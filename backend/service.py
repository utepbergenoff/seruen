import asyncio
import math


from .cache import ResponseCache
from .fallback import drafts
from .generate import AIError, Gemini, validate_drafts
from .geo import budget_for, in_astana, target_time, speed
from .intent import merge_intent, rule_intent
from .loader import load_pois
from .provider_status import log_provider
from .places import maps_url
from .retrieval import Retriever, SearchResult
from .safety import message, safety_notes
from .schemas import Considered, Coords, Recommendation, RecommendResponse


def display_time(now, lang):
    weekdays = {
        "ru": ("пн", "вт", "ср", "чт", "пт", "сб", "вс"),
        "kk": ("дс", "сс", "ср", "бс", "жм", "сб", "жс"),
        "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    }
    return f"{weekdays[lang][now.weekday()]} {now:%H:%M}"


class RecommendationService:
    def __init__(self, settings, provider=None):
        self.settings = settings
        self.dataset = load_pois(settings.poi_path)
        if any(p.poi_id.startswith("sample_") for p in self.dataset.pois):
            settings.data_kind = "sample"
        self.retriever = Retriever(self.dataset, settings.index_path)
        self.provider = provider or Gemini(settings)
        self.cache = ResponseCache(settings.cache_size)
        self.metrics = {"invented_ids_rejected": 0, "invalid_drafts_rejected": 0, "ai_errors": 0}

    def inspect(self, request, intent=None, current=None):
        intent = intent or rule_intent(request)
        now = target_time(request, intent, current)
        if not in_astana(request.location.lat, request.location.lon) or not intent.relevant or intent.unsafe:
            return intent, now, SearchResult([], [], 0, False, 0, 0, self.retriever.mode)
        search = self.retriever.search(request, intent, now, self.settings.airport_reserve_min)
        if (
            not search.hits
            and intent.categories
            and not any(word in request.query.casefold() for word in ("только", "only", "тек "))
        ):
            alternative = self.retriever.search(
                request, intent.model_copy(update={"categories": []}), now, self.settings.airport_reserve_min
            )
            if alternative.hits:
                alternative.category_relaxed = True
                search = alternative
        return intent, now, search

    def refusal(self, request, intent):
        if not in_astana(request.location.lat, request.location.lon):
            return "out"
        if intent.unsafe:
            return "unsafe"
        if not intent.relevant:
            return "unrelated"
        return None

    async def recommend(self, request, use_cache=True, force_no_ai=False, current=None):
        rules = rule_intent(request)
        now = target_time(request, rules, current)
        ai_enabled = bool(self.settings.gemini_api_key) and not force_no_ai and not self.settings.mock
        variant = f"{ai_enabled}:{self.settings.gemini_model}:{self.settings.mock}:{self.settings.airport_reserve_min}"
        key = self.cache.key(request, now, self.dataset.fingerprint, variant)
        cached = self.cache.get(key) if use_cache else None
        if cached:
            # Re-check hours and hard constraints at the exact request time, including half-hour boundaries.
            _, exact, check = self.inspect(request, rules, current)
            allowed = {h.poi.poi_id: h for h in check.hits}
            if (
                all(r.poi_id in allowed and r.open_status == allowed[r.poi_id].status for r in cached.recommendations)
                and cached.recommendations
            ):
                cached.mode = "cached"
                cached.considered.time = display_time(exact, rules.lang)
                cached.considered.target_time = exact
                return cached, "none"
        intent, now, search = self.inspect(request, rules, current)
        result_drafts = drafts(search.hits, intent)
        mode, intent_source, error = "no_ai", "rules", "none"
        ai_ids = set()
        if ai_enabled and search.hits and not self.refusal(request, intent):
            try:
                async with asyncio.timeout(self.settings.ai_timeout_s):
                    # Both AI operations share the same eight-second deadline.
                    ai_intent = await self.provider.intent(request, rules)
                    intent = merge_intent(rules, ai_intent, request)
                    intent, now, search = self.inspect(request, intent, current)
                    intent_source = "ai"
                    if search.hits:
                        generated = await self.provider.generate(request, intent, search.hits)
                        result_drafts, invented, rejected = validate_drafts(generated, search.hits, intent.lang)
                        self.metrics["invented_ids_rejected"] += invented
                        self.metrics["invalid_drafts_rejected"] += rejected
                        if not result_drafts:
                            raise AIError("all_drafts_rejected")
                        error = "invented_id_rejected" if invented else "draft_rejected" if rejected else "none"
                        mode = "ai"
                        ai_ids = {d.poi_id for d in result_drafts}
                        # Gemini often picks a single place. The next best checked candidates fill the cards
                        # up to three with template texts, so each card says honestly who chose it.
                        result_drafts = result_drafts + drafts(
                            [h for h in search.hits if h.poi.poi_id not in ai_ids], intent
                        )
                    else:
                        result_drafts = []
            except Exception as exc:
                # Keep the public contract stable; diagnostics contain only bounded codes.
                safe_codes = {"missing_key", "invalid_model", "provider_http_error", "provider_oversized",
                              "provider_incomplete", "provider_timeout", "provider_invalid_response",
                              "all_drafts_rejected", "invalid_generation_schema"}
                code = exc.code if isinstance(exc, AIError) and exc.code in safe_codes else (
                    "deadline_exceeded" if isinstance(exc, TimeoutError) else "invalid_or_unexpected_response"
                )
                log_provider("gemini", code)
                self.metrics["ai_errors"] += 1
                # Deterministic fallback restarts from rules, not a partially completed AI intent.
                intent, now, search = self.inspect(request, rules, current)
                result_drafts = drafts(search.hits, intent)
                intent_source, error, ai_ids = "rules", "ai_unavailable", set()
        response = self.assemble(request, intent, now, search, result_drafts, mode, intent_source, error, ai_ids)
        if use_cache:
            ttl = 1800 - (now.timestamp() % 1800)
            if error == "ai_unavailable":
                ttl = min(ttl, 30)  # Recover promptly after a transient provider outage.
            self.cache.put(key, response, ttl)
        return response, error

    def assemble(self, request, intent, now, search, selected, mode, intent_source, error, ai_ids=None, data_kind=None):
        cards, notes = [], []
        data_kind = data_kind or self.settings.data_kind
        lookup = {h.poi.poi_id: h for h in search.hits}
        for draft in selected:
            if len(cards) == 3:
                break
            # ai_ids=None keeps the old meaning: in AI mode every card was written by the AI.
            source = "ai" if mode == "ai" and (ai_ids is None or draft.poi_id in ai_ids) else "template"
            hit = lookup.get(draft.poi_id)
            if not hit:
                continue
            p, c = hit.poi, hit.candidate
            remaining = intent.time_budget_min - search.reserve - 2 * c.walk_min
            stay = min(remaining, max(math.ceil(hit.stay * 0.7), min(int(hit.stay * 1.3), draft.time_to_spend_min)))
            if stay <= 0:
                continue
            budget = budget_for(c.walk_min, stay, search.reserve)
            google = maps_url(p)
            links = (
                {}
                if data_kind == "sample"
                else {"2gis": f"https://2gis.kz/astana/geo/{p.lon},{p.lat}", "google": google}
            )
            cards.append(
                Recommendation(
                    poi_id=p.poi_id,
                    name=(p.name_kk if intent.lang == "kk" else p.name_en if intent.lang == "en" else p.name) or p.name,
                    category=p.category,
                    coords=Coords(lat=p.lat, lon=p.lon),
                    distance_m=c.distance_m,
                    walk_min=c.walk_min,
                    why=draft.why,
                    why_source=source,
                    time_to_spend_min=stay,
                    what_to_do=draft.what_to_do,
                    what_to_do_source=source,
                    open_status=hit.status,
                    description_source=p.description_source,
                    description=p.description,
                    description_url=p.description_url,
                    sources=p.sources,
                    last_checked=p.last_checked,
                    accessibility=p.wheelchair,
                    links=links,
                    rating=p.rating,
                    rating_count=p.rating_count,
                    budget_breakdown=budget,
                )
            )
        refusal = self.refusal(request, intent)
        if refusal:
            notes.append(message(refusal, intent.lang))
        elif not cards:
            notes.append(message("empty", intent.lang))
        if search.expanded:
            notes.append(message("expanded", intent.lang))
        if search.category_relaxed:
            notes.append(message("alternative", intent.lang))
        if any(c.open_status.state == "unknown" for c in cards):
            notes.append(message("unknown", intent.lang))
        if any(not lookup[c.poi_id].poi.description for c in cards):
            notes.append(message("limited", intent.lang))
        if intent.before_flight:
            notes.append(message("flight", intent.lang))
        if error == "ai_unavailable":
            notes.append(message("ai_fallback", intent.lang))
        if data_kind == "sample":
            notes.append(message("sample", intent.lang))
        if self.settings.mock:
            notes.append(message("mock", intent.lang))
        if request.context.simulate and request.context.now:
            notes.append(message("simulation", intent.lang).format(time=now.strftime("%d.%m.%Y %H:%M")))
        filters = [
            *intent.tags,
            *[f"category:{c}" for c in intent.categories],
            *[f"exclude:{c}" for c in intent.exclude_categories],
        ]
        if intent.companions == "child":
            filters.append("child_friendly")
        if request.context.accessibility:
            filters.append("wheelchair_confirmed")
        if search.category_relaxed:
            filters.append("category_relaxed_with_notice")
        return RecommendResponse(
            candidates=[h.candidate for h in search.hits],
            excluded=sorted(search.excluded, key=lambda c: c.distance_m)[:20],
            excluded_count=len(search.excluded),
            mode=mode,
            recommendations=cards,
            budget_breakdown=cards[0].budget_breakdown if cards else None,
            considered=Considered(
                location_rounded_to_m=max(100, request.location.precision_m),
                radius_m=math.floor(search.radius),
                radius_expanded=search.expanded,
                time_budget_min=intent.time_budget_min,
                effective_budget_min=max(0, intent.time_budget_min - search.reserve),
                reserve_min=search.reserve,
                walk_speed_m_per_min=speed(request, intent, now),
                companions=intent.companions,
                time_simulated=bool(request.context.simulate and request.context.now),
                lang=intent.lang,
                filters=filters,
                time=display_time(now, intent.lang),
                target_time=now,
                candidates_found=search.found,
                weather=request.context.weather,
                retrieval_mode=search.mode,
                intent_source=intent_source,
            ),
            notes=notes,
            safety=safety_notes(request, now, intent.lang),
            disclaimer=message("disclaimer", intent.lang),
            data_kind=data_kind,
            mock=self.settings.mock,
        )

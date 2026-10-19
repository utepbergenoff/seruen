"""Stateless plans: trusted POIs, arrival-time checks and bounded external routing."""

import math
from datetime import datetime, timedelta, timezone

from .activities import outdoor_walk_place
from .discovery import ENDPOINT, QUERIES, search_intent, to_poi
from .feature_data import apply_feedback, relaxation_options
from .geo import ALMATY, haversine, in_astana, speed, target_time
from .hours import open_status, schedule_open
from .intent import rule_intent
from .places import PlacesError
from .plan_models import (ComfortView, OfflinePlan, OfflineStop, PlanBudget, PlanExclusion, PlanLeg,
                          PlanRequest, PlanResponse, PlanState, PlanStop)
from .routing import WalkingRouter
from .safety import message, safety_notes
from .schemas import Coords, Location
from .twogis import FIELDS, IDENTIFIER

STAY = {"coffee": 20, "food": 30, "park": 20, "kids": 25, "culture": 30, "viewpoint": 15,
        "shopping": 20, "sport": 25, "night": 30, "unusual": 20, "library": 30, "cowork": 40}
TEXT = {
    "changed": ("План пересчитан по оставшемуся времени; выполненные и пропущенные места исключены.",
                "The plan uses remaining time and excludes completed and skipped places.",
                "Жоспар қалған уақытқа сай жаңартылды; барған және өткізіп жіберген орындар алынып тасталды."),
    "estimate": ("Минуты — оценка; расчёт не гарантирует время прибытия или доступность проходов.",
                 "Minutes are estimates, not a guarantee of arrival or accessible paths.",
                 "Минуттар шамамен есептелген; келу уақыты мен жолдың қолжетімділігіне кепілдік берілмейді."),
    "empty": ("Подходящих остановок нет. Ограничения сохранены; можно изменить время или фильтры.",
              "No suitable stops. Constraints are preserved; change the time or filters if you wish.",
              "Сәйкес аялдамалар жоқ. Шектеулер сақталды; уақытты немесе сүзгілерді өзгертуге болады."),
    "offline": ("Сохранённый снимок может устареть. После подключения обновите часы и условия; карта офлайн не включена.",
                "Saved information may be outdated. Refresh hours and conditions online; offline maps are not included.",
                "Сақталған мәлімет ескіруі мүмкін. Желіге қосылғанда уақыт пен шарттарды жаңартыңыз; офлайн карта жоқ."),
}


def text(key, lang):
    return TEXT[key][{"ru": 0, "en": 1, "kk": 2}[lang]]


class PlanError(Exception):
    def __init__(self, code, status=422):
        self.code, self.status = code, status
        super().__init__(code)


class Planner:
    def __init__(self, service, discovery, routing_transport=None):
        self.service, self.discovery = service, discovery
        self.features, self.settings = service.features, service.settings
        self.router = WalkingRouter(self.settings, routing_transport)

    def local(self, pid):
        return self.features.pois.get(self.features.canonical(pid))

    async def resolve(self, pid, request):
        # Explicit remote IDs are resolved remotely, never silently replaced with OSM facts.
        if not pid.startswith("2gis_"):
            p = self.local(pid)
            if p is None:
                raise PlanError("poi_not_found", 404)
            return p
        cached = self.discovery.cached_poi(pid)
        if cached:
            return cached
        ident = pid.removeprefix("2gis_")
        if not IDENTIFIER.fullmatch(ident):
            raise PlanError("poi_not_found", 404)
        self.discovery.check_enabled()
        result = await self.discovery.provider.request_items(ENDPOINT + "/byid", {
            "id": ident, "locale": "ru_KZ", "fields": FIELDS + ",items.rubrics",
        })
        for item in result.get("items", []):
            if item.get("id") == ident:
                poi = to_poi(item, request, 50000)
                if poi:
                    self.discovery.remember_poi(poi)
                    return poi
        raise PlanError("poi_not_found", 404)

    async def pool(self, request, destination):
        if request.source == "2gis" or (request.source == "auto" and self.discovery.active()):
            self.discovery.check_enabled()
            intent, query = search_intent(request)
            if request.preferences.preferred_categories:
                query = QUERIES[request.preferences.preferred_categories[0]]
            elif request.preferences.indoor_only:
                # Generic "warm place" text is not a business name in the catalogue.
                query = QUERIES["coffee"]
            # Search near the trip corridor rather than apply round-trip filters to a one-way plan.
            center = Location(lat=(request.location.lat + destination.lat) / 2,
                              lon=(request.location.lon + destination.lon) / 2)
            search_request = request.model_copy(update={"location": center})
            import hashlib
            key = hashlib.sha256((search_request.model_dump_json() + ":plan_pool").encode()).hexdigest()
            result = []
            for page in (1, 2):
                body = await self.discovery.page(key, search_request, query, 5000, page)
                for item in body.get("items", []):
                    try:
                        poi = to_poi(item, search_request, 5000)
                    except (ValueError, TypeError, AttributeError):
                        continue
                    if poi:
                        self.discovery.remember_poi(poi)
                        result.append(poi)
                if page * 10 >= body.get("total", 0) or not body.get("items"):
                    break
            return result, "2gis"
        return [p for pid, p in self.features.pois.items() if pid not in self.features.comfort], "local"

    def rejection(self, poi, req, intent, arrival, departure, walking, explicit=False):
        if req.preferences.max_distance_m is not None and haversine(
                req.location.lat, req.location.lon, poi.lat, poi.lon) > req.preferences.max_distance_m:
            return "distance_limit"
        comfort = self.features.comfort.get(poi.poi_id)
        reason = self.features.constraint(poi, req.preferences, walking, arrival.date(), comfort=bool(comfort))
        if reason:
            return reason
        if comfort:
            if not self.features.verified(comfort.evidence, arrival.date(), 30):
                return "comfort_unverified"
            if comfort.access == "unknown":
                return "comfort_access_unknown"
        if poi.category in intent.exclude_categories:
            return "excluded_category"
        if intent.companions == "child" and (poi.adult_only or poi.category == "night" or not poi.kid_friendly):
            return "not_child_friendly"
        if not comfort:
            # A person may explicitly pick a catalog place outside the inferred search category.
            # Explicit preference filters, child/accessibility checks and schedules still apply.
            allowed = req.preferences.preferred_categories or ([] if explicit else intent.categories)
            if "coffee" in allowed:
                allowed = list(set(allowed) | {"food"})
            if allowed and poi.category not in allowed:
                return "category_mismatch"
            if not explicit and "outdoor_walk" in intent.tags and not outdoor_walk_place(poi):
                return "category_mismatch"
        if req.context.accessibility and poi.wheelchair != "yes":
            return "accessibility_unconfirmed"
        if poi.temporary and not (poi.event_start and poi.event_end and poi.event_source
                                  and poi.event_start <= arrival and departure <= poi.event_end):
            return "event_unverified"
        # Check each minute, including split-day/overnight schedules and closing during the visit.
        if (poi.opening_hours_raw or poi.published_special_hours) and poi.hours_source != "none":
            try:
                minute = arrival
                while minute < departure:
                    raw = poi.published_special_hours.get(str(minute.date()), poi.opening_hours_raw)
                    if raw and not schedule_open(raw, minute):
                        return "closed_at_visit"
                    minute += timedelta(minutes=1)
            except ValueError:
                pass  # unknown schedule stays explicitly unknown in the output
        night = any(x.hour >= 22 or x.hour < 6 for x in (arrival, departure))
        if night and not (poi.indoor or {"lit", "busy", "освещено", "людно"} & set(poi.tags)):
            return "night_safety_unconfirmed"
        if night and walking > math.ceil(1000 * 1.3 / speed(req, intent, arrival)):
            return "night_walk_limit"
        weather = req.context.weather
        if weather and (weather.temp_c <= -15 or weather.wind_ms >= 10) and walking > math.ceil(
            500 * 1.3 / speed(req, intent, arrival)
        ):
            return "weather_walk_limit"
        return None

    async def build(self, payload, current=None, use_current_time=False):
        req = apply_feedback(payload.request)
        if req.end is not None and "finish_mode" not in payload.model_fields_set:
            payload = payload.model_copy(update={"finish_mode": "destination", "destination": req.end})
        prefs = req.preferences
        combined = list(dict.fromkeys([*prefs.exclude_poi_ids, *payload.completed_ids, *payload.skipped_ids]))
        # Preserve every exclusion; reject oversize state instead of silently dropping old exclusions.
        if len(combined) > 200:
            raise PlanError("too_many_exclusions")
        prefs.exclude_poi_ids = combined
        intent = rule_intent(req)
        if use_current_time:
            intent.when = "now"
        now = target_time(req, intent, current)
        walking_speed = speed(req, intent, now)
        origin = payload.origin or req.location
        finish = payload.destination if payload.finish_mode == "destination" else origin
        if any(not in_astana(p.lat, p.lon) for p in (req.location, origin, finish)):
            raise PlanError("outside_astana")
        if prefs.atmosphere_example_id and not any(r.example_id == prefs.atmosphere_example_id
                                                  for r in self.features.examples(now.date())):
            raise PlanError("atmosphere_example_unavailable", 404)
        available = intent.time_budget_min
        reserve = max(payload.reserve_min, self.settings.airport_reserve_min if intent.before_flight else 0)
        source = "2gis" if req.source == "2gis" or (req.source == "auto" and self.discovery.active()) else "local"
        excluded, notes = [], [text("estimate", intent.lang), *safety_notes(req, now, intent.lang)]
        if req.feedback:
            notes.append(text("changed", intent.lang))
        refusal = self.service.refusal(req, intent)
        if refusal == "unrelated" and payload.stop_ids:
            # A verified explicit place ID is sufficient intent for building a route.
            # Unsafe requests and points outside Astana still refuse normally.
            refusal = None
        source_error, candidates = None, []
        if refusal:
            notes.append(message(refusal, intent.lang))
        else:
            try:
                if payload.stop_ids:
                    for pid in payload.stop_ids:
                        if self.features.canonical(pid) in {self.features.canonical(x) for x in combined}:
                            excluded.append(PlanExclusion(poi_id=pid, reason="completed_or_skipped"))
                            continue
                        candidates.append(await self.resolve(pid, req))
                    if any(p.poi_id.startswith("2gis_") for p in candidates):
                        source = "2gis"
                else:
                    candidates, source = await self.pool(req, finish)
            except PlacesError as exc:
                source_error = exc.code
                candidates = []
        semantics = dict(zip([p.poi_id for p in self.service.retriever.pois],
                             self.service.retriever.relevance(req.query)))
        if not payload.stop_ids:
            def priority(p):
                detour = haversine(req.location.lat, req.location.lon, p.lat, p.lon) + haversine(p.lat, p.lon, finish.lat, finish.lon)
                visual = self.features.match(p.poi_id, prefs.atmosphere_example_id, now.date(), prefs.atmosphere_profile)
                return (-semantics.get(p.poi_id, 0) - .2 * len(visual.matched_features) + detour / 10000, p.poi_id)
            candidates.sort(key=priority)
        chosen, seen = [], set()
        points = [req.location, finish]
        routed = self.router.estimate(points, walking_speed)
        # Choose stops using bounded estimates, then validate actual street legs once.
        for poi in candidates:
            canonical = self.features.canonical(poi.poi_id)
            if canonical in seen:
                continue
            seen.add(canonical)
            if len(chosen) >= payload.max_stops:
                break
            stay = 5 if poi.poi_id in self.features.comfort else STAY.get(poi.category, 20)
            trial = [*chosen, (poi, stay)]
            est = self.router.estimate([req.location, *[Coords(lat=p.lat, lon=p.lon) for p, _ in trial], finish], walking_speed)
            arrival = now + timedelta(minutes=sum(est.minutes[:-1]) + sum(s for _, s in chosen))
            departure = arrival + timedelta(minutes=stay)
            reason = self.rejection(poi, req, intent, arrival, departure, est.minutes[-2], explicit=bool(payload.stop_ids))
            if not reason and prefs.max_walk_min is not None and est.minutes[-1] > prefs.max_walk_min:
                reason = "finish_walk_limit"
            if not reason and sum(est.minutes) + sum(s for _, s in trial) + reserve > available:
                reason = "over_budget"
            if reason:
                excluded.append(PlanExclusion(poi_id=poi.poi_id, reason=reason))
            else:
                chosen = trial
        # Two bounded calls maximum: initial selected route, one repair after dropping invalid stops.
        for attempt in range(2):
            points = [req.location, *[Coords(lat=p.lat, lon=p.lon) for p, _ in chosen], finish]
            routed = (self.router.estimate(points, walking_speed) if refusal or source_error
                      else await self.router.route(points, walking_speed))
            cursor, invalid = now, []
            for i, (poi, stay) in enumerate(chosen):
                arrival = cursor + timedelta(minutes=routed.minutes[i])
                departure = arrival + timedelta(minutes=stay)
                reason = self.rejection(poi, req, intent, arrival, departure, routed.minutes[i], explicit=bool(payload.stop_ids))
                if reason:
                    invalid.append(poi.poi_id)
                    excluded.append(PlanExclusion(poi_id=poi.poi_id, reason=reason))
                cursor = departure
            over = sum(routed.minutes) + sum(s for _, s in chosen) + reserve > available
            if not invalid and not over:
                break
            if attempt == 1 or not chosen:
                break
            if invalid:
                chosen = [(p, s) for p, s in chosen if p.poi_id not in invalid]
            elif over:
                dropped, _ = chosen.pop()
                excluded.append(PlanExclusion(poi_id=dropped.poi_id, reason="street_route_over_budget"))
        stops, cursor = [], now
        invalid_final = False
        for i, (poi, stay) in enumerate(chosen):
            arrival = cursor + timedelta(minutes=routed.minutes[i])
            departure = arrival + timedelta(minutes=stay)
            invalid_final |= bool(self.rejection(poi, req, intent, arrival, departure, routed.minutes[i], explicit=bool(payload.stop_ids)))
            stops.append(PlanStop(poi_id=poi.poi_id, canonical_id=self.features.canonical(poi.poi_id), name=poi.name, category=poi.category,
                                  coords=Coords(lat=poi.lat, lon=poi.lon), arrival_at=arrival,
                                  departure_at=departure, stay_min=stay, open_status=open_status(poi, arrival),
                                  visit_condition=self.features.condition(poi.poi_id, arrival.date(), poi),
                                  atmosphere_match=self.features.match(poi.poi_id, prefs.atmosphere_example_id,
                                                                      arrival.date(), prefs.atmosphere_profile), sources=poi.sources))
            cursor = departure
        ids = ["start", *[p.poi_id for p, _ in chosen], "finish"]
        legs = [PlanLeg(from_id=ids[i], to_id=ids[i+1], distance_m=d, walk_min=routed.minutes[i], source=routed.source)
                for i, d in enumerate(routed.distances)]
        total = sum(routed.minutes) + sum(s for _, s in chosen) + reserve
        # The final leg is part of the walk too: tired/cold/max-walk must not disappear
        # merely because there is no POI at the destination to run through rejection().
        finish_limit = prefs.max_walk_min
        finish_at = now + timedelta(minutes=total-reserve)
        if any(t.hour >= 22 or t.hour < 6 for t in (cursor, finish_at)):
            finish_limit = min(finish_limit or 480, math.ceil(1000 * 1.3 / walking_speed))
        weather = req.context.weather
        if weather and (weather.temp_c <= -15 or weather.wind_ms >= 10):
            finish_limit = min(finish_limit or 480, math.ceil(500 * 1.3 / walking_speed))
        if finish_limit is not None and routed.minutes[-1] > finish_limit:
            invalid_final = True
            excluded.append(PlanExclusion(poi_id="finish", reason="finish_walk_limit"))
        fits = total <= available and not invalid_final and not refusal and source_error is None
        status = "ok" if fits else "impossible"
        if not chosen and fits:
            status = "no_matches"
            notes.append(text("empty", intent.lang))
        elif fits and payload.stop_ids and len(stops) < len(payload.stop_ids):
            status = "partial"
        if source_error:
            status = "unavailable"
        if refusal:
            status = "refused"
        warning_codes = ["estimated_arrival", "plan_not_navigation"]
        if routed.source == "distance_estimate":
            warning_codes.append("street_route_unavailable")
        if any(p.open_status.state in ("unknown", "likely_open") for p in stops):
            warning_codes.append("hours_unconfirmed")
        if not fits:
            warning_codes.append("do_not_start_plan")
        state = PlanState(created_at=datetime.now(timezone.utc), origin=origin, finish_mode=payload.finish_mode,
                          finish=finish, remaining_ids=[p.poi_id for p in stops], completed_ids=payload.completed_ids,
                          skipped_ids=payload.skipped_ids, preferences=prefs,
                          exclude_categories=intent.exclude_categories, companions=intent.companions,
                          accessibility=req.context.accessibility, reserve_min=reserve)
        return PlanResponse(status=status, fits=fits, stops=stops, legs=legs,
                            budget=PlanBudget(available_min=available, walking_min=sum(routed.minutes),
                                              visiting_min=sum(s for _, s in chosen), reserve_min=reserve,
                                              total_min=total, spare_min=max(0, available-total)),
                            state=state, departure_at=now, estimated_arrival_at=now + timedelta(minutes=total-reserve),
                            routing_source=routed.source, routing_error=routed.error, geometry=routed.geometry,
                            exclusions=excluded[:100], notes=notes, warning_codes=warning_codes,
                            applied_preferences=prefs, change_codes=[req.feedback.reason] if req.feedback else [],
                            relaxation_options=relaxation_options(prefs) if not stops else [],
                            data_kind=self.settings.data_kind, source=source, source_error=source_error)

    async def replan(self, payload):
        state, req = payload.previous, payload.request.model_copy(deep=True)
        previous_intent = rule_intent(req)
        req.context.companions = state.companions if "companions" in state.model_fields_set else previous_intent.companions
        if "accessibility" in state.model_fields_set:
            req.context.accessibility = state.accessibility
        reserve = max(payload.reserve_min, state.reserve_min,
                      self.settings.airport_reserve_min if previous_intent.before_flight else 0)
        # Replanning preserves previous filters unless the frontend explicitly sends a replacement snapshot.
        if "preferences" not in payload.request.model_fields_set:
            req.preferences = state.preferences.model_copy(deep=True)
        if "exclude_categories" not in payload.request.context.model_fields_set:
            from .schemas import Context
            req.context.exclude_categories = Context(exclude_categories=state.exclude_categories).exclude_categories
        age = (datetime.now(timezone.utc) - state.created_at).total_seconds()
        if age < -60 or age > 86400:
            raise PlanError("stale_plan", 409)
        if not set(payload.completed_ids) <= set(state.remaining_ids):
            raise PlanError("completion_not_in_plan")
        completed = list(dict.fromkeys([*state.completed_ids, *payload.completed_ids]))
        skipped = list(state.skipped_ids)
        if payload.reason in ("skip", "closed", "busy"):
            if payload.poi_id not in state.remaining_ids:
                raise PlanError("stop_not_in_plan")
            skipped = list(dict.fromkeys([*skipped, payload.poi_id]))
        if len(completed) > 200 or len(skipped) > 200:
            raise PlanError("too_many_exclusions")
        req.context.time_budget_min = payload.remaining_time_min
        if payload.keep_stops and payload.reason in ("cold", "tired"):
            return await self.nearby_break(payload, req, completed, skipped, reserve)
        if payload.keep_stops and payload.reason == "add_stop":
            return await self.insert_break(payload, req, completed, skipped, reserve, payload.poi_id)
        if payload.reason == "cold":
            req.preferences.indoor_only = True
            req.preferences.max_walk_min = min(req.preferences.max_walk_min or 120, 5)
            # Replace outdoor intent explicitly when the person asks to warm up.
            req.query = {"en": "warm indoor place", "kk": "жылы жабық орын қайда", "ru": "тёплое место рядом"}.get(
                req.context.lang, "тёплое место рядом")
        if payload.reason == "tired":
            req.preferences.max_walk_min = min(req.preferences.max_walk_min or 120, 5)
        remaining = [x for x in state.remaining_ids if x not in completed and x not in skipped]
        if payload.reason == "add_stop":
            remaining.append(payload.poi_id)
            if len(set(remaining)) != len(remaining) or len(remaining) > 5:
                raise PlanError("duplicate_or_too_many_stops")
        if payload.reason in ("cold", "closed", "busy"):
            remaining = []  # Request a replacement under preserved exclusions and current preferences.
        result = await self.build(PlanRequest(request=req, origin=state.origin,
                                              finish_mode=state.finish_mode, destination=state.finish,
                                              stop_ids=remaining, completed_ids=completed, skipped_ids=skipped,
                                              reserve_min=reserve, max_stops=5), use_current_time=True)
        # A fitting return leg without stops is not a replacement walking plan.
        # Older clients accept no_matches as success and would erase the current walk.
        if result.status == "no_matches":
            raise PlanError("no_replacement_found", 409)
        result.change_codes = [payload.reason]
        result.notes.insert(0, text("changed", rule_intent(req).lang))
        return result

    async def nearby_break(self, payload, req, completed, skipped, reserve):
        """Suggest one nearby indoor break without losing any uncompleted stop or finish."""
        state = payload.previous
        remaining = [p for p in state.remaining_ids if p not in completed and p not in skipped]
        if not remaining or len(remaining) >= 5:
            raise PlanError("no_replacement_found", 409)
        nearby = req.model_copy(deep=True)
        nearby.preferences.atmosphere_example_id = None
        nearby.preferences.atmosphere_profile = None
        nearby.preferences.atmosphere_verified_only = False
        nearby.preferences.preferred_categories = []
        nearby.preferences.indoor_only = True
        nearby.preferences.max_walk_min = min(nearby.preferences.max_walk_min or 120, 5)
        nearby.preferences.exclude_poi_ids = list(dict.fromkeys([
            *nearby.preferences.exclude_poi_ids, *remaining]))
        if len(nearby.preferences.exclude_poi_ids) > 200:
            raise PlanError("too_many_exclusions")
        nearby.query = {"ru": "тёплое место рядом", "kk": "жылы жабық орын қайда",
                        "en": "warm indoor place"}.get(req.context.lang, "warm indoor place")
        nearby.end = None
        goal = await self.resolve(remaining[0], req)
        candidates = []
        if payload.reason == "tired" and not req.preferences.indoor_only:
            candidates.extend(r.poi for r in self.features.comfort.values() if r.kind == "bench"
                and r.access == "public" and self.features.verified(r.evidence, datetime.now(ALMATY).date(), 30))
        # Search the forward corridor, then validate the chosen stop together with every original stop.
        try:
            pool, _ = await self.pool(nearby, Coords(lat=goal.lat, lon=goal.lon))
            candidates.extend(p for p in pool if p.indoor)
        except PlacesError:
            pass
        eligible = []
        for poi in candidates:
            metric = forward_break(req.location, Coords(lat=goal.lat, lon=goal.lon), poi)
            if metric is not None and poi.poi_id not in remaining + completed + skipped:
                eligible.append((metric, poi))
        eligible.sort(key=lambda pair: (0 if payload.reason == "tired" and pair[1].poi_id in self.features.comfort else 1,
                                       pair[0], pair[1].poi_id))
        for _, poi in eligible[:4]:
            try:
                return await self.insert_break(payload, req, completed, skipped, reserve, poi.poi_id)
            except PlanError as exc:
                if exc.status != 409:
                    raise
        raise PlanError("no_on_route_break", 409)

    async def insert_break(self, payload, req, completed, skipped, reserve, pause_id):
        state = payload.previous
        remaining = [p for p in state.remaining_ids if p not in completed and p not in skipped]
        if not remaining or len(remaining) >= 5 or pause_id in remaining + completed + skipped:
            raise PlanError("no_replacement_found", 409)
        goal = await self.resolve(remaining[0], req)
        pause = await self.resolve(pause_id, req)
        goal_coords = Coords(lat=goal.lat, lon=goal.lon)
        if forward_break(req.location, goal_coords, pause) is None:
            raise PlanError("break_not_on_route", 409)
        original_preferences = req.preferences.model_copy(deep=True)
        # An emergency rest need not match the café's decor. Keep budget, exclusions and safety filters.
        req = req.model_copy(deep=True)
        req.preferences.atmosphere_example_id = None
        req.preferences.atmosphere_profile = None
        req.preferences.atmosphere_verified_only = False
        req.preferences.preferred_categories = []
        required = [pause_id, *remaining]
        result = await self.build(PlanRequest(request=req, origin=state.origin,
            finish_mode=state.finish_mode, destination=state.finish, stop_ids=required,
            completed_ids=completed, skipped_ids=skipped, reserve_min=reserve, max_stops=len(required)),
            use_current_time=True)
        if (not result.fits or [p.poi_id for p in result.stops] != required
                or not result.legs or result.legs[0].walk_min > min(req.preferences.max_walk_min or 120, 5 if payload.reason == "cold" else 10)):
            raise PlanError("no_replacement_found", 409)
        # Reject actual street detours too. With an unavailable router this remains a labelled estimate.
        direct = haversine(req.location.lat, req.location.lon, goal.lat, goal.lon) * 1.3
        baseline_minutes = self.router.estimate([req.location, goal_coords], speed(req, rule_intent(req), result.departure_at)).minutes[0]
        if (sum(leg.distance_m for leg in result.legs[:2]) - direct > 180
                or sum(leg.walk_min for leg in result.legs[:2]) - baseline_minutes > 3):
            raise PlanError("break_detour_too_long", 409)
        result.state.preferences = original_preferences
        result.applied_preferences = original_preferences
        for stop in result.stops:
            if stop.poi_id not in self.features.comfort:
                stop.atmosphere_match = self.features.match(stop.poi_id, original_preferences.atmosphere_example_id,
                    stop.arrival_at.date(), original_preferences.atmosphere_profile)
        result.change_codes = [payload.reason, "nearby_break_keeps_stops"]
        result.notes.insert(0, {"ru": "Предложена остановка по направлению к следующей цели (добавочный путь — не более 3 минут по оценке). Прежние остановки и финиш сохранены; проверьте условия доступа.",
            "en": "Suggested a break towards your next stop (estimated extra walk: at most 3 minutes). All remaining stops and the finish are kept; check access conditions.",
            "kk": "Келесі мақсатқа қарай аялдау ұсынылды (қосымша жол шамамен 3 минуттан аспайды). Бұрынғы аялдамалар мен соңғы нүкте сақталды; кіру шарттарын тексеріңіз."
            }.get(req.context.lang, "Indoor break suggested; remaining stops and finish kept."))
        return result

    async def refresh(self, payload):
        if not payload.saved.stops:
            raise PlanError("empty_saved_plan")
        finish = payload.saved.finish or payload.request.location
        return await self.build(PlanRequest(request=payload.request, finish_mode="destination", destination=finish,
                                            stop_ids=[s.poi_id for s in payload.saved.stops],
                                            reserve_min=payload.reserve_min, max_stops=5))

    def comfort(self, payload):
        points = payload.route_points or [payload.location]
        if any(not in_astana(p.lat, p.lon) for p in points + [payload.location]):
            raise PlanError("outside_astana")
        if payload.on_route_only and len(points) < 2:
            raise PlanError("route_destination_required")
        today = datetime.now(ALMATY).date()
        result = []
        for pid, record in self.features.comfort.items():
            verified = self.features.verified(record.evidence, today, 30)
            if payload.verified_only and not verified or payload.kinds and record.kind not in payload.kinds:
                continue
            if payload.public_only and record.access != "public":
                continue
            distance = distance_to_path(record.poi, points)
            if distance > payload.radius_m:
                continue
            extra = None
            if payload.on_route_only:
                if len(points) < 2:
                    raise PlanError("route_destination_required")
                extra = forward_break(payload.location, points[-1], record.poi)
                if extra is None:
                    continue
            result.append(ComfortView(poi_id=pid, name=record.poi.name,
                                      coords=Coords(lat=record.poi.lat, lon=record.poi.lon), kind=record.kind,
                                      extra_walk_min=math.ceil(extra / 60) if extra is not None else None, access=record.access, distance_to_route_m=math.ceil(distance), floor=record.floor,
                                      note=record.evidence.note, source_url=str(record.evidence.source_url),
                                      checked_at=record.evidence.checked_at, verified=verified,
                                      distance_m=math.ceil(haversine(payload.location.lat, payload.location.lon, record.poi.lat, record.poi.lon)),
                                      walk_min=math.ceil(haversine(payload.location.lat, payload.location.lon, record.poi.lat, record.poi.lon) * 1.3 / 60),
                                      indoor=record.poi.indoor, open_status=open_status(record.poi, datetime.now(ALMATY))))
        return sorted(result, key=lambda r: (r.distance_to_route_m, r.poi_id))[:50]

    async def export(self, payload):
        result = await self.build(payload.plan)
        lang = rule_intent(payload.plan.request).lang
        stops, omitted = [], []
        for stop in result.stops:
            record = self.features.owned.get(self.features.canonical(stop.poi_id))
            if not record or not record.offline_allowed or not self.features.verified(
                record.evidence, result.departure_at.date()
            ):
                omitted.append(stop.poi_id)
                continue
            p = record.poi  # Only team-licensed facts, never substitute the remote catalogue response.
            stops.append(OfflineStop(poi_id=p.poi_id, name=p.name, coords=Coords(lat=p.lat, lon=p.lon),
                                     category=p.category, stay_min=stop.stay_min, sources=p.sources,
                                     checked_at=record.evidence.checked_at, license=record.license,
                                     attribution=record.attribution))
        valid = result.fits and result.status in ("ok", "partial")
        complete = bool(stops) and not omitted and valid
        return OfflinePlan(saved_at=datetime.now(timezone.utc),
                           status="saved" if valid and stops else "not_exportable" if valid else "revalidation_failed",
                           stops=stops if valid else [], omitted_ids=omitted, contains_full_route=complete,
                           budget=result.budget if complete else None,
                           origin=result.state.origin if complete else None, finish=result.state.finish if complete else None,
                           warning_codes=["snapshot_not_current", "offline_map_not_included",
                                          *(["restricted_content_omitted"] if omitted else [])],
                           notes=[text("offline", lang)])


def distance_to_path(poi, points):
    """Distance to the supplied polyline, not just its endpoints; metres, city-scale projection."""
    if len(points) == 1:
        return haversine(poi.lat, poi.lon, points[0].lat, points[0].lon)
    scale = 111195
    cos = math.cos(math.radians(poi.lat))
    best = float("inf")
    for a, b in zip(points, points[1:]):
        ax, ay = (a.lon-poi.lon)*scale*cos, (a.lat-poi.lat)*scale
        bx, by = (b.lon-poi.lon)*scale*cos, (b.lat-poi.lat)*scale
        dx, dy = bx-ax, by-ay
        t = max(0, min(1, -(ax*dx+ay*dy)/(dx*dx+dy*dy))) if dx or dy else 0
        best = min(best, math.hypot(ax+t*dx, ay+t*dy))
    return best


def forward_break(start, goal, poi):
    """Conservative city-scale corridor: no backwards stops and at most 180 m added walking.

    We do not call a straight line street navigation. insert_break also checks routed legs.
    A near-zero projection is allowed only for a stop already at the current position.
    """
    scale = 111195
    cos = math.cos(math.radians(start.lat))
    gx, gy = (goal.lon-start.lon)*scale*cos, (goal.lat-start.lat)*scale
    px, py = (poi.lon-start.lon)*scale*cos, (poi.lat-start.lat)*scale
    length = math.hypot(gx, gy)
    if length < 15:
        return None
    progress = (px*gx + py*gy) / length
    cross = abs(px*gy - py*gx) / length
    before, after = math.hypot(px, py), math.hypot(px-gx, py-gy)
    extra = max(0, (before + after - length) * 1.3)
    if progress < 0 or progress > length or cross > 100 or before > 450 or after > length + 5 or extra > 180:
        return None
    return extra

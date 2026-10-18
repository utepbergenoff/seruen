"""Nearby 2GIS retrieval and grounded Gemini selection; no permanent catalog import."""

import asyncio
import hashlib
import json
import math
import re
import secrets
import time
from collections import OrderedDict
from datetime import datetime, timezone

from .fallback import drafts
from .feature_data import apply_feedback
from .generate import AIError, validate_drafts
from .geo import haversine, in_astana, radius_for, speed, target_time
from .hours import open_status
from .intent import rule_intent
from .loader import Dataset
from .places import PlacesError
from .provider_status import log_provider
from .retrieval import Retriever, SearchResult
from .schemas import CatalogPlace, Coords, POI
from .twogis import DAYS, FIELDS, IDENTIFIER, intervals

ENDPOINT = "https://catalog.api.2gis.com/3.0/items"
TTL = 300
PAGE_SIZE = 10
BATCH_PAGES = 2
QUERIES = {"coffee": "Кофейни", "food": "Кафе", "park": "Парки культуры и отдыха", "kids": "Детские развлекательные центры",
           "culture": "Достопримечательности", "viewpoint": "Достопримечательности", "shopping": "Торговые центры",
           "sport": "Спортивные площадки", "night": "Кафе", "unusual": "Достопримечательности",
           "library": "Библиотеки", "cowork": "Коворкинги"}
# Classify only the provider's rubrics, never invent a category from the user's request.
CATEGORIES = [
    ("night", r"\bбар(?:ы|ов)?\b|ночн|pub|nightclub|кальян"),
    ("kids", r"детск.{0,35}(площад|игров|развлек|клуб|центр досуга)|playground|children.{0,30}(play|entertain)|kids.{0,30}(play|entertain)|балалар.{0,30}(ойын|көңіл)"),
    ("coffee", r"кофейн|кофе|coffee"),
    ("food", r"ресторан|кафе|столов|пекар|restaurant|cafe|асхана"),
    ("park", r"\bпарк(?:и|ов)?\b|сквер|\bсад\b|\bparks?\b|garden|саябақ"),
    ("library", r"библиот|library|кітапхана"),
    ("cowork", r"коворкин|cowork"),
    ("shopping", r"торгов|трц|shopping|сауда"),
    ("sport", r"спорт|стадион|бассейн|sport|swim"),
    ("culture", r"музе|театр|галере|кинотеатр|museum|theatre|cinema|культур|достопримеч|памятник"),
    ("viewpoint", r"смотров|обзор|набереж|viewpoint|observation"),
]
MESSAGES = {
    "ru": {
        "source": "Данные 2ГИС: поиск «{q}». Ближайшие места загружаются порциями.",
        "unavailable": "Не удалось получить места из 2ГИС ({code}). Попробуйте позже. Места из локальной базы не подставлены.",
        "expired": "Поиск устарел. Нажмите «Подобрать», чтобы начать заново.",
        "why": "Найдено в 2ГИС; прогулка с возвращением укладывается в ваш бюджет времени.",
        "limit": "Достигнут предел просмотра этого поиска. Уточните запрос или измените точку на карте.",
    },
    "kk": {
        "source": "2ГИС деректері: «{q}» іздеу. Маңайдағы орындар бөліктермен жүктеледі.",
        "unavailable": "2ГИС орындарын алу мүмкін болмады ({code}). Кейінірек қайталаңыз. Жергілікті база қолданылмады.",
        "expired": "Іздеу мерзімі аяқталды. Жаңадан іздеңіз.",
        "why": "2ГИС-тен табылды; барып-қайту серуені уақыт шегіне сай келеді.",
        "limit": "Іздеу шегіне жеттіңіз. Сұрауды немесе картадағы нүктені өзгертіңіз.",
    },
    "en": {
        "source": "2GIS data: search for “{q}”. Nearby places are loaded in batches.",
        "unavailable": "Could not obtain places from 2GIS ({code}). Try later. Local database places were not substituted.",
        "expired": "This search expired. Start a new search.",
        "why": "Found in 2GIS; the visit and return walk fit your time budget.",
        "limit": "This search reached its browsing limit. Refine the query or move the map point.",
    },
}


def search_intent(request):
    intent = rule_intent(request)
    text = request.query.strip()
    # A short business name such as Starbucks is a legitimate catalog search.
    if (not intent.relevant and 1 < len(text) <= 80
            and not re.search(r"такси|taxi|код|python|рецепт|лечени|лекарств|юрид|закон|bitcoin|крипт|ignore|instruction",
                              text, re.I)):
        intent.relevant = True
    explicit = [("library", r"библиот|library|кітапхана"), ("cowork", r"коворкин|cowork"),
                ("food", r"ресторан|restaurant|поесть"), ("park", r"парк|park|саябақ"),
                ("culture", r"музей|museum|мұражай"), ("shopping", r"трц|shopping|торгов")]
    if intent.companions != "child":
        for category, pattern in explicit:
            if re.search(pattern, text, re.I):
                intent.categories = [category]
                break
    query = QUERIES.get(intent.categories[0], "") if intent.categories else text[:100]
    # Preserve short business names containing a category word (e.g. Coffee Boom).
    if (1 < len(text.split()) <= 5 and len(text) <= 80 and not re.search(
            r"хочу|нуж|найд|ищу|рядом|поблиз|погуля|прогуля|кофе и|тих|спокой|работ|ноут|розет|минут|час|ребен|дет|"
            r"want|need|near|quiet|work|laptop|minute|hour|with|coffee and|қайда|жақын|тыныш|серуен", text, re.I)):
        query = text
    return intent, query or "Достопримечательности"


def schedule_text(item):
    """Only complete weekly schedules, without seasonal or special-hour ambiguity."""
    value = item.get("schedule") or {}
    if not isinstance(value, dict) or item.get("schedule_special") or any(
        value.get(k) for k in ("date_from", "date_to", "comment", "description")
    ):
        return None
    if value.get("is_24x7") is True:
        return "24/7"
    if not all(day in value for day in DAYS):
        return None
    return "; ".join(f"{day[:2]} " + (",".join(f"{i.start}-{i.end}" for i in intervals(value[day])) or "off")
                     for day in DAYS)


def to_poi(item, request, radius):
    if not isinstance(item, dict) or item.get("type") not in ("branch", "attraction"):
        return None
    ident, point, name = item.get("id"), item.get("point") or {}, item.get("name")
    if not isinstance(ident, str) or not IDENTIFIER.fullmatch(ident) or not isinstance(name, str):
        return None
    lat, lon = point.get("lat"), point.get("lon")
    if (type(lat) not in (float, int) or type(lon) not in (float, int)
            or not math.isfinite(lat) or not math.isfinite(lon) or not in_astana(lat, lon)
            or haversine(request.location.lat, request.location.lon, lat, lon) > radius):
        return None
    rubric_names = [str(r.get("name", "")) for r in item.get("rubrics", []) if isinstance(r, dict)]
    # Clothes, toy and sports-equipment shops are not playgrounds or sports venues.
    rubrics = " ".join(r for r in rubric_names if not re.search(
        r"одежд|обув|инвентар|товар|оборудован|магазин|игруш|сувенир|clothing|footwear|toy store", r, re.I))
    categories = [cat for cat, pattern in CATEGORIES if re.search(pattern, rubrics, re.I)]
    preferred = rule_intent(request).categories
    category = next((cat for cat in preferred if cat in categories), next(iter(categories), None))
    if category is None and item.get("type") == "attraction":
        category = "culture"
    if category is None:
        return None
    reviews = item.get("reviews") or {}
    rating = reviews.get("rating", reviews.get("general_rating"))
    count = reviews.get("review_count", reviews.get("general_review_count"))
    rating = rating if type(rating) in (int, float) and 0 < rating <= 5 else None
    count = count if type(count) is int and count >= 0 else None
    try:
        hours = schedule_text(item)
    except (ValueError, TypeError, KeyError):
        hours = None
    return POI(poi_id=f"2gis_{ident}", name=name[:200], lat=lat, lon=lon, category=category,
               twogis_place_id=ident, sources=["2gis"], description=rubrics[:2000], description_source="source",
               description_url=f"https://2gis.kz/astana/{'firm' if item['type'] == 'branch' else 'geo'}/{ident}",
               opening_hours_raw=hours, hours_source="2gis" if hours else "none", hours_conflict=True,
               rating=rating, rating_count=count, popularity=(rating or 0)/5,
               last_checked=datetime.now(timezone.utc).date(),
               kid_friendly=bool({"kids", "park"} & set(categories)), adult_only="night" in categories,
               indoor=category in ("coffee", "food", "library", "cowork", "shopping", "night"))


class Discovery:
    def __init__(self, provider, service):
        self.provider, self.service = provider, service
        self.pages, self.cursors = OrderedDict(), OrderedDict()
        self.ai_cache = OrderedDict()
        self.photo_pois = OrderedDict()
        self.lock = asyncio.Lock()
        self.ai_lock = asyncio.Lock()

    def remember_poi(self, poi):
        # Provider-verified identity for photos. Same short TTL as catalogue pages;
        # no persistent catalogue, user coordinates or extra provider requests.
        self.photo_pois[poi.poi_id] = (time.monotonic(), poi)
        self.photo_pois.move_to_end(poi.poi_id)
        while len(self.photo_pois) > 320:
            self.photo_pois.popitem(last=False)

    def cached_poi(self, poi_id):
        saved = self.photo_pois.get(poi_id)
        if saved and time.monotonic() - saved[0] < TTL:
            return saved[1]
        self.photo_pois.pop(poi_id, None)
        return None

    def active(self):
        s = self.provider.settings
        return s.twogis_enabled and s.twogis_search_enabled and not s.mock

    def check_enabled(self):
        if not self.active():
            raise PlacesError("twogis_disabled")
        if not self.provider.settings.twogis_api_key:
            raise PlacesError("twogis_not_configured")

    async def page(self, key, request, query, radius, page):
        async with self.lock:
            now = time.monotonic()
            cached = self.pages.get((key, page))
            if cached and now - cached[0] < TTL:
                return cached[1]
            params = {"q": query, "point": f"{request.location.lon},{request.location.lat}",
                      "radius": math.ceil(radius), "page_size": PAGE_SIZE, "page": page,
                      "locale": "ru_KZ", "sort": "distance",
                      "fields": FIELDS + ",items.rubrics"}
            try:
                result = await self.provider.request_items(ENDPOINT, params, max_bytes=1_000_000)
            except PlacesError as exc:
                if exc.code != "twogis_not_found":
                    raise
                result = {"items": [], "total": 0}
            if len(result.get("items", [])) > PAGE_SIZE or type(result.get("total", 0)) is not int:
                raise PlacesError("twogis_invalid_response", 502)
            self.pages[(key, page)] = (now, result)
            self.pages.move_to_end((key, page))
            while len(self.pages) > 16:
                self.pages.popitem(last=False)
            return result

    def cursor(self, key, page, seen):
        token = secrets.token_urlsafe(24)
        self.cursors[token] = (time.monotonic(), key, page, frozenset(seen))
        while len(self.cursors) > 128:
            self.cursors.popitem(last=False)
        return token

    async def choose(self, key, request, intent, hits):
        fallback = drafts(hits, intent)
        settings = self.service.settings
        if not hits or not settings.gemini_api_key or settings.mock:
            return fallback, "no_ai", set(), "none"
        cache_key = (key, settings.gemini_model, tuple(h.poi.poi_id for h in hits))
        try:
            async with self.ai_lock:
                cached = self.ai_cache.get(cache_key)
                if cached and cached[1] is None and time.monotonic() - cached[0] < 30:
                    return fallback, "no_ai", set(), "ai_unavailable"
                if cached and cached[1] is not None and time.monotonic() - cached[0] < TTL:
                    generated = cached[1]
                else:
                    async with asyncio.timeout(settings.ai_timeout_s):
                        generated = await self.service.provider.generate(request, intent, hits)
                    self.ai_cache[cache_key] = (time.monotonic(), generated)
                    while len(self.ai_cache) > 64:
                        self.ai_cache.popitem(last=False)
            accepted, invented, rejected = validate_drafts(generated, hits, intent.lang)
            self.service.metrics["invented_ids_rejected"] += invented
            self.service.metrics["invalid_drafts_rejected"] += rejected
            if not accepted:
                raise AIError("all_drafts_rejected")
            ai_ids = {d.poi_id for d in accepted}
            return accepted + drafts([h for h in hits if h.poi.poi_id not in ai_ids], intent), "ai", ai_ids, "none"
        except Exception as exc:
            # A retry click must not hammer an exhausted free quota; allow recovery after 30 s.
            self.ai_cache[cache_key] = (time.monotonic(), None)
            self.ai_cache.move_to_end(cache_key)
            while len(self.ai_cache) > 64:
                self.ai_cache.popitem(last=False)
            self.service.metrics["ai_errors"] += 1
            safe_codes = {"missing_key", "invalid_model", "provider_http_error", "provider_oversized",
                          "provider_incomplete", "provider_timeout", "provider_invalid_response",
                          "invalid_generation_schema", "all_drafts_rejected"}
            code = exc.code if isinstance(exc, AIError) and exc.code in safe_codes else (
                "deadline_exceeded" if isinstance(exc, TimeoutError) else "invalid_or_unexpected_response"
            )
            log_provider("gemini", "catalog_" + code)
            return fallback, "no_ai", set(), "ai_unavailable"

    async def recommend(self, request, current=None):
        request = apply_feedback(request)
        intent, query = search_intent(request)
        if request.preferences.preferred_categories:
            intent.categories = request.preferences.preferred_categories.copy()
            query = QUERIES[intent.categories[0]]
        # A cafe/restaurant that 2GIS finds for coffee is a valid candidate too.
        # Keep its real category; do not relabel all such businesses as coffee shops.
        if "coffee" in intent.categories and "food" not in intent.categories:
            intent.categories.append("food")
        now = target_time(request, intent, current)
        msg = MESSAGES[intent.lang]
        reserve = min(self.service.settings.airport_reserve_min, intent.time_budget_min) if intent.before_flight else 0
        radius = min(5000, radius_for(intent.time_budget_min - reserve, speed(request, intent, now),
                                     now.hour >= 22 or now.hour < 6) * 1.5)
        if request.end:
            radius = min(5000, radius * 2)
        if request.preferences.max_distance_m is not None:
            radius = min(radius, request.preferences.max_distance_m)
        empty = SearchResult([], [], radius, False, 0, reserve, "2gis")
        response = self.service.assemble(request, intent, now, empty, [], "no_ai", "rules", "none", data_kind="real")
        response.source, response.data_kind = "2gis", "real"
        if self.service.refusal(request, intent) or radius <= 0:
            return response, "none"
        key = hashlib.sha256(json.dumps(request.model_dump(mode="json", exclude={"cursor", "request_id"}),
                                       sort_keys=True).encode()).hexdigest()
        page, seen = 1, frozenset()
        try:
            self.check_enabled()
            if request.cursor:
                saved = self.cursors.get(request.cursor)
                if not saved or saved[1] != key or time.monotonic() - saved[0] >= TTL:
                    raise PlacesError("twogis_search_expired", 409)
                _, _, page, seen = saved
                cached = self.pages.get((key, page))
                if cached and time.monotonic() - cached[0] >= TTL:
                    raise PlacesError("twogis_search_expired", 409)
            pois, items = {}, {}
            more, total, partial_error = False, 0, None
            for _ in range(BATCH_PAGES):
                try:
                    result = await self.page(key, request, query, radius, page)
                except PlacesError as exc:
                    if not items:
                        raise
                    partial_error, more = exc.code, True
                    break
                total = result.get("total", len(result.get("items", [])))
                for item in result.get("items", []):
                    try:
                        poi = to_poi(item, request, radius)
                    except (ValueError, TypeError, AttributeError):
                        continue
                    if poi and poi.poi_id not in seen:
                        pois[poi.poi_id], items[poi.poi_id] = poi, item
                        self.remember_poi(poi)
                more = bool(result.get("items")) and page * PAGE_SIZE < total
                page += 1
                if not more:
                    break
            retriever = Retriever(Dataset(list(pois.values()), "2gis", 0, 0), None, self.service.features)
            search = retriever.search(request, intent, now, self.service.settings.airport_reserve_min, diversify=False)
            search.mode = "2gis"
            selected, mode, ai_ids, ai_error = await self.choose(key, request, intent, search.hits)
            response = self.service.assemble(request, intent, now, search, selected,
                                             mode, "rules", ai_error, ai_ids, data_kind="real")
            response.source, response.data_kind = "2gis", "real"
            for card in response.recommendations:
                poi, item = pois[card.poi_id], items[card.poi_id]
                address = item.get("address_name")
                card.facts_source, card.address = "2gis", address[:1000] if isinstance(address, str) else None
                card.links["2gis"] = poi.description_url
            # Browsing includes closed or otherwise ineligible places with an explicit reason.
            # Hard filters continue to apply to recommendations and Gemini's candidate list.
            all_candidates = [h.candidate for h in search.hits] + search.excluded
            for candidate in sorted(all_candidates, key=lambda c: (c.distance_m, c.poi_id)):
                if candidate.excluded_because in ("category_mismatch", "excluded_category", "excluded_place",
                                                   "already_visited", "preferred_category_mismatch"):
                    continue
                poi, item = pois[candidate.poi_id], items[candidate.poi_id]
                address = item.get("address_name")
                response.nearby_places.append(CatalogPlace(
                    poi_id=poi.poi_id, canonical_id=self.service.features.canonical(poi.poi_id), name=poi.name, category=poi.category,
                    coords=Coords(lat=poi.lat, lon=poi.lon), distance_m=candidate.distance_m,
                    walk_min=candidate.walk_min, address=address[:1000] if isinstance(address, str) else None,
                    rating=poi.rating, rating_count=poi.rating_count, open_status=open_status(poi, now),
                    eligible=candidate.excluded_because is None, excluded_because=candidate.excluded_because,
                    links={"2gis": poi.description_url}))
            response.catalog_total = total
            response.notes.insert(0, msg["source"].format(q=query))
            if more:
                response.next_cursor = self.cursor(key, page, seen | pois.keys())
            if partial_error:
                response.source_error = partial_error
                response.notes.append(msg["unavailable"].format(code=partial_error))
            return response, partial_error or ai_error
        except PlacesError as exc:
            self.provider.last_status = exc.code
            log_provider("twogis_search", exc.code)
            response.source_error = exc.code
            response.notes = [msg["expired"] if exc.code == "twogis_search_expired"
                              else msg["unavailable"].format(code=exc.code)]
            return response, exc.code

    async def details(self, poi_id, language):
        self.check_enabled()
        ident = poi_id.removeprefix("2gis_")
        if not IDENTIFIER.fullmatch(ident):
            raise PlacesError("poi_not_found", 404)
        result = await self.provider.request_items(ENDPOINT + "/byid", {
            "id": ident, "locale": "kk_KZ" if language == "kk" else "ru_KZ", "fields": FIELDS,
        })
        try:
            item = next(i for i in result.get("items", []) if i.get("id") == ident)
            point = item["point"]
            if not in_astana(point["lat"], point["lon"]):
                raise PlacesError("twogis_not_found", 404)
            return self.provider.format_details(item, poi_id, "kk" if language == "kk" else "ru")
        except (ValueError, TypeError, KeyError, StopIteration):
            raise PlacesError("twogis_invalid_response", 502) from None

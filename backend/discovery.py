"""Request-time 2GIS discovery. No import into the POI file, disk index or Gemini."""

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
from .geo import haversine, in_astana, radius_for, speed, target_time
from .intent import rule_intent
from .loader import Dataset
from .places import PlacesError
from .provider_status import log_provider
from .retrieval import Retriever, SearchResult
from .schemas import POI
from .twogis import DAYS, FIELDS, IDENTIFIER, intervals

ENDPOINT = "https://catalog.api.2gis.com/3.0/items"
TTL = 300
PAGE_SIZE = 50
MAX_PAGES = 5
QUERIES = {"coffee": "Кофейни", "food": "Кафе", "park": "Парки", "kids": "Детские развлекательные центры",
           "culture": "Достопримечательности", "viewpoint": "Достопримечательности", "shopping": "Торговые центры",
           "sport": "Спортивные площадки", "night": "Кафе", "unusual": "Достопримечательности",
           "library": "Библиотеки", "cowork": "Коворкинги"}
# Classify only the provider's rubrics, never invent a category from the user's request.
CATEGORIES = [
    ("night", r"бар\b|ночн|клуб|pub|nightclub|кальян"),
    ("kids", r"детск|балалар|playground|children|kids"),
    ("coffee", r"кофейн|кофе|coffee"),
    ("food", r"ресторан|кафе|столов|пекар|restaurant|cafe|асхана"),
    ("park", r"парк|сквер|сад\b|park|garden|саябақ"),
    ("library", r"библиот|library|кітапхана"),
    ("cowork", r"коворкин|cowork"),
    ("shopping", r"торгов|трц|shopping|сауда"),
    ("sport", r"спорт|стадион|бассейн|sport|swim"),
    ("culture", r"музе|театр|галере|кинотеатр|museum|theatre|cinema|культур|достопримеч|памятник"),
    ("viewpoint", r"смотров|обзор|набереж|viewpoint|observation"),
]
MESSAGES = {
    "ru": {
        "source": "Данные 2ГИС: поиск «{q}». Показаны подходящие места из текущей страницы каталога, а не вся Астана.",
        "unavailable": "Не удалось получить места из 2ГИС ({code}). Попробуйте позже. Места из локальной базы не подставлены.",
        "expired": "Поиск устарел. Нажмите «Подобрать», чтобы начать заново.",
        "why": "Найдено в 2ГИС; прогулка с возвращением укладывается в ваш бюджет времени.",
        "limit": "Достигнут предел просмотра этого поиска. Уточните запрос или измените точку на карте.",
    },
    "kk": {
        "source": "2ГИС деректері: «{q}» іздеу. Бүкіл Астана емес, каталогтың ағымдағы бетіндегі сәйкес орындар көрсетілген.",
        "unavailable": "2ГИС орындарын алу мүмкін болмады ({code}). Кейінірек қайталаңыз. Жергілікті база қолданылмады.",
        "expired": "Іздеу мерзімі аяқталды. Жаңадан іздеңіз.",
        "why": "2ГИС-тен табылды; барып-қайту серуені уақыт шегіне сай келеді.",
        "limit": "Іздеу шегіне жеттіңіз. Сұрауды немесе картадағы нүктені өзгертіңіз.",
    },
    "en": {
        "source": "2GIS data: search for “{q}”. These are suitable places from the current catalog page, not all of Astana.",
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
    rubrics = " ".join(str(r.get("name", "")) for r in item.get("rubrics", []) if isinstance(r, dict))
    category = next((cat for cat, pattern in CATEGORIES if re.search(pattern, rubrics, re.I)), None)
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
               kid_friendly=category in ("kids", "park"), adult_only=category == "night",
               indoor=category in ("coffee", "food", "library", "cowork", "shopping", "night"))


class Discovery:
    def __init__(self, provider, service):
        self.provider, self.service = provider, service
        self.pages, self.cursors = OrderedDict(), OrderedDict()
        self.lock = asyncio.Lock()

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
                      "locale": "ru_KZ", "type": "branch,attraction", "sort": "distance",
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

    def cursor(self, key, page, offset):
        token = secrets.token_urlsafe(24)
        self.cursors[token] = (time.monotonic(), key, page, offset)
        while len(self.cursors) > 128:
            self.cursors.popitem(last=False)
        return token

    async def recommend(self, request, current=None):
        intent, query = search_intent(request)
        now = target_time(request, intent, current)
        msg = MESSAGES[intent.lang]
        reserve = min(self.service.settings.airport_reserve_min, intent.time_budget_min) if intent.before_flight else 0
        radius = min(5000, radius_for(intent.time_budget_min - reserve, speed(request, intent, now),
                                     now.hour >= 22 or now.hour < 6) * 1.5)
        empty = SearchResult([], [], radius, False, 0, reserve, "2gis")
        response = self.service.assemble(request, intent, now, empty, [], "no_ai", "rules", "none", data_kind="real")
        response.source, response.data_kind = "2gis", "real"
        if self.service.refusal(request, intent) or radius <= 0:
            return response, "none"
        key = hashlib.sha256(json.dumps(request.model_dump(mode="json", exclude={"cursor"}),
                                       sort_keys=True).encode()).hexdigest()
        page, offset = 1, 0
        try:
            self.check_enabled()
            if request.cursor:
                saved = self.cursors.get(request.cursor)
                if not saved or saved[1] != key or time.monotonic() - saved[0] >= TTL:
                    raise PlacesError("twogis_search_expired", 409)
                _, _, page, offset = saved
                cached = self.pages.get((key, page))
                if cached and time.monotonic() - cached[0] >= TTL:
                    raise PlacesError("twogis_search_expired", 409)
            result = await self.page(key, request, query, radius, page)
            pois, items = {}, {}
            previous_ids = {item.get("id") for (page_key, page_no), (_, old) in self.pages.items()
                            if page_key == key and page_no < page
                            for item in old.get("items", []) if isinstance(item, dict)}
            for item in result.get("items", []):
                try:
                    if isinstance(item, dict) and item.get("id") in previous_ids:
                        continue
                    poi = to_poi(item, request, radius)
                except (ValueError, TypeError, AttributeError):
                    continue
                if poi:
                    pois[poi.poi_id], items[poi.poi_id] = poi, item
            retriever = Retriever(Dataset(list(pois.values()), "2gis", 0, 0), None)
            search = retriever.search(request, intent, now, self.service.settings.airport_reserve_min, diversify=False)
            search.mode = "2gis"
            selected = search.hits[offset:offset+3]
            shown = SearchResult(search.hits[:10], search.excluded, search.radius, search.expanded,
                                 search.found, search.reserve, "2gis")
            # Keep the selected candidates visible on later pages, too.
            shown.hits = selected + [h for h in search.hits if h not in selected][:7]
            response = self.service.assemble(request, intent, now, shown, drafts(selected, intent),
                                             "no_ai", "rules", "none", data_kind="real")
            response.source, response.data_kind = "2gis", "real"
            for card in response.recommendations:
                poi, item = pois[card.poi_id], items[card.poi_id]
                address = item.get("address_name")
                card.facts_source, card.address, card.why = "2gis", address[:1000] if isinstance(address, str) else None, msg["why"]
                card.links["2gis"] = poi.description_url
            response.notes.insert(0, msg["source"].format(q=query))
            if offset + 3 < len(search.hits):
                response.next_cursor = self.cursor(key, page, offset + 3)
            elif page * PAGE_SIZE < result.get("total", 0):
                if page < MAX_PAGES:
                    response.next_cursor = self.cursor(key, page+1, 0)
                else:
                    response.notes.append(msg["limit"])
            return response, "none"
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

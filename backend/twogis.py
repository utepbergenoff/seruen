"""On-demand 2GIS details. No bulk collection, startup calls, or RAG enrichment."""

import asyncio
import math
import re
import time
import unicodedata
from collections import deque
from datetime import datetime, timezone
from typing import Literal

import httpx
from pydantic import Field

from .geo import haversine, in_astana
from .places import PlacesError
from .provider_status import log_provider
from .schemas import Model

FIELDS = "items.point,items.name_ex,items.schedule,items.schedule_special,items.reviews,items.attribute_groups"
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
IDENTIFIER = re.compile(r"[0-9]{1,32}")
CLOCK = r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$|^24:00$"


class HoursInterval(Model):
    start: str = Field(pattern=CLOCK)
    end: str = Field(pattern=CLOCK)


class DayHours(Model):
    day: Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    intervals: list[HoursInterval] = Field(max_length=12)


class SpecialHours(Model):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    intervals: list[HoursInterval] = Field(max_length=12)


class TwoGisDetails(Model):
    poi_id: str
    twogis_place_id: str = Field(pattern=r"^[0-9]{1,32}$")
    source: Literal["2gis"] = "2gis"
    provider_name: str = Field(min_length=1, max_length=500)
    address: str | None = Field(default=None, max_length=1000)
    language: Literal["ru", "kk"]
    checked_at: datetime
    match_method: Literal["stored_id", "exact_name_nearby", "catalog_id"]
    match_distance_m: int = Field(ge=0, le=150)
    rating: float | None = Field(default=None, ge=0, le=5, strict=True)
    rating_count: int | None = Field(default=None, ge=0, strict=True)
    rating_scope: Literal["branch", "organization", "unknown"] = "unknown"
    weekly_hours: list[DayHours] = Field(default_factory=list, max_length=7)
    special_hours: list[SpecialHours] = Field(default_factory=list, max_length=100)
    is_24x7: bool | None = Field(default=None, strict=True)
    schedule_note: str | None = Field(default=None, max_length=2000)
    open_now: None = None
    provider_url: str
    attribution: Literal["Данные 2ГИС"] = "Данные 2ГИС"
    photos_supported: Literal[False] = False


def normalized(value):
    return "".join(c for c in unicodedata.normalize("NFKC", value or "").casefold() if c.isalnum())


def intervals(value):
    if not isinstance(value, dict):
        raise ValueError("invalid hours")
    return [HoursInterval(start=x["from"], end=x["to"]) for x in value.get("working_hours", [])]


def review_values(reviews):
    """Keep rating/count from the same scope, including an explicitly null branch rating."""
    rating, count = reviews.get("rating"), reviews.get("review_count")
    scope = "organization" if reviews.get("is_org_reviews") is True else "branch"
    if rating is None or (type(rating) in (int, float) and rating == 0 and reviews.get("general_rating") is not None):
        rating, count, scope = reviews.get("general_rating"), reviews.get("general_review_count"), "unknown"
    if type(rating) in (int, float) and rating == 0:
        rating = None
    return rating, count, scope


class TwoGis:
    def __init__(self, settings, pois, transport=None):
        self.settings, self.transport = settings, transport
        self.pois = {p.poi_id: p for p in pois}
        self.last_status = "not_checked" if settings.twogis_api_key else "not_configured"
        self.lock, self.calls = asyncio.Lock(), deque()
        self.day, self.day_calls = None, 0
        self.blocked_until, self.blocked_code = 0.0, None

    async def reserve(self):
        # Secondary process-local guard. The demo key's total quota is enforced by 2GIS.
        # Failed attempts count; restarts reset this local guard, not the provider quota.
        async with self.lock:
            now, today = time.monotonic(), datetime.now(timezone.utc).date()
            if self.day != today:
                self.day, self.day_calls = today, 0
            while self.calls and self.calls[0] <= now - 60:
                self.calls.popleft()
            if (len(self.calls) >= self.settings.twogis_requests_per_minute
                    or self.day_calls >= self.settings.twogis_requests_per_day):
                raise PlacesError("twogis_local_limit", 429)
            self.calls.append(now)
            self.day_calls += 1

    async def fetch(self, poi, language):
        params = {"key": self.settings.twogis_api_key, "fields": FIELDS,
                  "locale": "kk_KZ" if language == "kk" else "ru_KZ"}
        if poi.twogis_place_id:
            endpoint = "https://catalog.api.2gis.com/3.0/items/byid"
            params["id"] = poi.twogis_place_id
        else:
            endpoint = "https://catalog.api.2gis.com/3.0/items"
            params.update(q=poi.name, point=f"{poi.lon},{poi.lat}", radius="150", page_size="10")
        return await self.request_items(endpoint, params)

    async def request_items(self, endpoint, params, max_bytes=200_000):
        params = {**params, "key": self.settings.twogis_api_key}
        try:
            if self.blocked_code and time.monotonic() < self.blocked_until:
                raise PlacesError(self.blocked_code, 429 if self.blocked_code == "twogis_quota_exceeded" else 503)
            await self.reserve()
            async with httpx.AsyncClient(timeout=self.settings.twogis_timeout_s,
                                         transport=self.transport, follow_redirects=False) as client:
                response = await client.get(endpoint, params=params)
            if response.status_code != 200:
                log_provider("twogis", f"http_{int(response.status_code)}")
                raise self.provider_error(response.status_code)
            if len(response.content) > max_bytes:
                raise ValueError("large response")
            data = response.json()
            code = data["meta"]["code"]
            if code != 200:
                if type(code) is int and 100 <= code <= 599:
                    log_provider("twogis", f"meta_{code}")
                raise self.provider_error(code)
            result = data["result"]
            if not isinstance(result, dict) or not isinstance(result.get("items", []), list):
                raise ValueError("invalid result")
            self.last_status = "ok"
            self.blocked_until, self.blocked_code = 0.0, None
            return result
        except PlacesError as exc:
            self.last_status = exc.code
            if exc.code in ("twogis_access_denied", "twogis_quota_exceeded") and time.monotonic() >= self.blocked_until:
                # Search and details share the guard. Do not hammer a refused demo key.
                self.blocked_until, self.blocked_code = time.monotonic() + 300, exc.code
            raise
        except httpx.TimeoutException:
            self.last_status = "twogis_timeout"
            raise PlacesError("twogis_timeout") from None
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            self.last_status = "twogis_invalid_response"
            # Exceptions/URLs can contain the key, required by 2GIS in the query string.
            raise PlacesError("twogis_invalid_response", 502) from None

    @staticmethod
    def provider_error(code):
        if code in (401, 403):
            return PlacesError("twogis_access_denied")
        if code in (402, 429):
            return PlacesError("twogis_quota_exceeded", 429)
        if code == 404:
            return PlacesError("twogis_not_found", 404)
        return PlacesError("twogis_unavailable")

    @staticmethod
    def match(poi, result):
        matches = {}
        names = {normalized(n) for n in (poi.name, poi.name_kk, poi.name_en) if n}
        items = result.get("items", [])
        if len(items) > 10 or result.get("total", len(items)) > len(items):
            raise PlacesError("twogis_match_ambiguous", 409)
        for item in items:
            ident, point = item.get("id", ""), item.get("point", {})
            if not isinstance(ident, str) or not IDENTIFIER.fullmatch(ident):
                continue
            lat, lon = point.get("lat"), point.get("lon")
            if (type(lat) not in (float, int) or type(lon) not in (float, int)
                    or not math.isfinite(lat) or not math.isfinite(lon) or not in_astana(lat, lon)):
                continue
            distance = haversine(poi.lat, poi.lon, lat, lon)
            if distance > 150:
                continue
            if poi.twogis_place_id:
                if ident == poi.twogis_place_id:
                    matches[ident] = (item, distance)
            else:
                parts = item.get("name_ex", {})
                variants = {normalized(n) for n in
                            (item.get("name"), parts.get("primary"), parts.get("short_name")) if isinstance(n, str)}
                if names & variants:
                    matches[ident] = (item, distance)
        if len(matches) != 1:
            raise PlacesError("twogis_match_ambiguous" if matches else "twogis_not_matched",
                              409 if matches else 404)
        return next(iter(matches.values()))

    async def details(self, poi_id, language="ru"):
        if not self.settings.twogis_enabled or self.settings.mock:
            raise PlacesError("twogis_disabled")
        if not self.settings.twogis_api_key:
            raise PlacesError("twogis_not_configured")
        poi = self.pois.get(poi_id)
        if poi is None:
            raise PlacesError("poi_not_found", 404)
        if not in_astana(poi.lat, poi.lon) or (poi.name_generic and not poi.twogis_place_id):
            raise PlacesError("twogis_not_matched", 404)
        language = "kk" if language == "kk" else "ru"
        try:
            item, distance = self.match(poi, await self.fetch(poi, language))
            return self.format_details(item, poi_id, language, distance,
                                       "stored_id" if poi.twogis_place_id else "exact_name_nearby")
        except PlacesError as exc:
            self.last_status = exc.code
            log_provider("twogis", exc.code)
            raise
        except (ValueError, TypeError, AttributeError, KeyError):
            self.last_status = "twogis_invalid_response"
            log_provider("twogis", self.last_status)
            raise PlacesError(self.last_status, 502) from None

    @staticmethod
    def format_details(item, poi_id, language="ru", distance=0, method="catalog_id"):
        schedule, reviews = item.get("schedule") or {}, item.get("reviews") or {}
        rating, count, scope = review_values(reviews)
        notes = [schedule.get(k) for k in ("comment", "description", "date_from", "date_to") if schedule.get(k)]
        return TwoGisDetails(
            poi_id=poi_id, twogis_place_id=item["id"], provider_name=item["name"],
            address=item.get("address_name"), language=language, checked_at=datetime.now(timezone.utc),
            match_method=method,
            match_distance_m=round(distance), rating=rating, rating_count=count, rating_scope=scope,
            weekly_hours=[DayHours(day=d, intervals=intervals(schedule[d])) for d in DAYS if d in schedule],
            special_hours=[SpecialHours(date=d["date"], intervals=intervals(d))
                           for d in item.get("schedule_special", [])],
            is_24x7=schedule.get("is_24x7"), schedule_note="; ".join(notes) or None,
            provider_url=f"https://2gis.kz/astana/{'firm' if item.get('type') == 'branch' else 'geo'}/{item['id']}",
        )

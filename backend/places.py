"""On-demand Places details; Google content never enters the POI index/AI/cache."""

import asyncio
import re
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from pydantic import Field, HttpUrl

from .provider_status import http_error_code, log_provider
from .schemas import Model

DETAIL_FIELDS = "id,rating,userRatingCount,currentOpeningHours,regularOpeningHours,businessStatus,attributions"
PLACE_ID = re.compile(r"[A-Za-z0-9_-]{1,255}")


class PlacesError(Exception):
    def __init__(self, code, status=503):
        self.code, self.status = code, status
        super().__init__(code)


class Attribution(Model):
    provider: str = Field(max_length=500)
    provider_uri: HttpUrl | None = None


class PlaceDetails(Model):
    poi_id: str
    google_place_id: str
    source: str = "google_maps"
    language: str
    checked_at: datetime
    rating: float | None = Field(default=None, ge=0, le=5, strict=True)
    rating_count: int | None = Field(default=None, ge=0, strict=True)
    open_now: bool | None = Field(default=None, strict=True)
    current_weekday_hours: list[str] = Field(default_factory=list, max_length=7)
    regular_weekday_hours: list[str] = Field(default_factory=list, max_length=7)
    business_status: str | None = None
    google_maps_url: str
    attributions: list[Attribution] = Field(default_factory=list, max_length=20)


def maps_url(poi, place_id=None):
    params = {"api": 1, "query": f"{poi.lat},{poi.lon}"}
    candidate = place_id or poi.google_place_id
    if candidate and PLACE_ID.fullmatch(candidate):
        params["query_place_id"] = candidate
    return "https://www.google.com/maps/search/?" + urlencode(params)


class Places:
    def __init__(self, settings, pois, transport=None):
        self.settings, self.transport = settings, transport
        self.pois = {p.poi_id: p for p in pois}
        self.probe_status = "not_configured"
        self.lock = asyncio.Lock()
        self.calls = deque()
        self.day, self.day_calls = None, 0

    async def fetch(self, place_id, fields, language="ru"):
        if not PLACE_ID.fullmatch(place_id):
            raise PlacesError("invalid_place_id", 422)
        if not self.settings.google_places_api_key:
            raise PlacesError("places_not_configured")
        try:
            async with httpx.AsyncClient(timeout=self.settings.google_places_timeout_s,
                                         transport=self.transport, follow_redirects=False) as client:
                response = await client.get(
                    f"https://places.googleapis.com/v1/places/{place_id}",
                    params={"languageCode": language},
                    headers={"X-Goog-Api-Key": self.settings.google_places_api_key,
                             "X-Goog-FieldMask": fields},
                )
            if response.status_code != 200:
                log_provider("google_places", http_error_code(response))
                raise PlacesError("place_not_found" if response.status_code == 404 else "places_unavailable",
                                  404 if response.status_code == 404 else 503)
            if len(response.content) > 100_000:
                raise PlacesError("places_invalid_response", 502)
            data = response.json()
            if not isinstance(data, dict) or data.get("id") != place_id:
                raise PlacesError("places_invalid_response", 502)
            return data
        except httpx.TimeoutException:
            log_provider("google_places", "timeout")
            raise PlacesError("places_timeout", 503) from None
        except (httpx.HTTPError, ValueError, TypeError):
            log_provider("google_places", "invalid_response")
            raise PlacesError("places_invalid_response", 502) from None

    async def probe(self):
        """One IDs Only request per process, even while billable details are disabled."""
        if not self.settings.google_places_api_key or self.settings.mock:
            return
        first = next((p.google_place_id for p in self.pois.values() if p.google_place_id), None)
        if not first:
            self.probe_status = "no_mapped_places"
            return
        try:
            await self.fetch(first, "id")
            self.probe_status = "ok"
            log_provider("google_places", "ids_probe_ok")
        except PlacesError as exc:
            self.probe_status = exc.code

    async def details(self, poi_id, language="ru"):
        if not self.settings.google_places_enabled or self.settings.mock:
            raise PlacesError("places_disabled")
        poi = self.pois.get(poi_id)
        if poi is None:
            raise PlacesError("poi_not_found", 404)
        if not poi.google_place_id:
            raise PlacesError("place_not_mapped", 404)
        # Secondary process-local guard only. Cloud quotas are required before enabling.
        # Reserve calls before awaiting I/O; failures also consume the guard.
        async with self.lock:
            now = time.monotonic()
            today = datetime.now(timezone.utc).date()
            if today != self.day:
                self.day, self.day_calls = today, 0
            while self.calls and self.calls[0] <= now - 60:
                self.calls.popleft()
            if len(self.calls) >= 5 or self.day_calls >= 25:
                raise PlacesError("places_local_limit", 429)
            self.calls.append(now)
            self.day_calls += 1
        language = "en" if language == "en" else "ru"
        data = await self.fetch(poi.google_place_id, DETAIL_FIELDS, language)
        try:
            current, regular = data.get("currentOpeningHours", {}), data.get("regularOpeningHours", {})
            return PlaceDetails(
                poi_id=poi_id, google_place_id=data["id"], language=language,
                checked_at=datetime.now(timezone.utc), rating=data.get("rating"),
                rating_count=data.get("userRatingCount"), open_now=current.get("openNow"),
                current_weekday_hours=current.get("weekdayDescriptions", []),
                regular_weekday_hours=regular.get("weekdayDescriptions", []),
                business_status=data.get("businessStatus"), google_maps_url=maps_url(poi),
                attributions=[Attribution(provider=a["provider"], provider_uri=a.get("providerUri"))
                              for a in data.get("attributions", [])],
            )
        except (ValueError, TypeError, AttributeError, KeyError):
            raise PlacesError("places_invalid_response", 502) from None

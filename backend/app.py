import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .config import ROOT, Settings
from .schemas import Context, Health, Location, RecommendRequest, RecommendResponse, Weather
from .service import RecommendationService
from .places import Places, PlaceDetails, PlacesError
from .twogis import TwoGis, TwoGisDetails
from .photos import Photos, PhotoRequest, PlacePhotos
from .discovery import Discovery
from .feature_api import register_features
from .experiences import register_experiences
from .plans import Planner, PlanError
from .geo import ALMATY

logger = logging.getLogger("seruen")


def scenarios():
    return json.loads((ROOT / "data/demo_scenarios.json").read_text(encoding="utf-8"))


def create_app(settings=None, provider=None, places_transport=None, twogis_transport=None, photos_transport=None,
               photos_ai=None, routing_transport=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.service = RecommendationService(settings, provider)
        service = app.state.service
        app.state.places = Places(settings, list(service.features.pois.values()), places_transport)
        app.state.twogis = TwoGis(settings, list(service.features.pois.values()), twogis_transport)
        app.state.discovery = Discovery(app.state.twogis, service)
        app.state.planner = Planner(service, app.state.discovery, routing_transport)
        app.state.photos = Photos(settings, list(service.features.pois.values()), photos_transport,
                                  photos_ai or getattr(service.provider, "structured", None) and service.provider,
                                  catalog_poi=app.state.discovery.cached_poi)
        await app.state.places.probe()
        logger.info(
            json.dumps(
                {
                    "mode": "startup",
                    "duration_ms": 0,
                    "candidates": len(service.dataset.pois),
                    "error_code": f"loader_rejected_{service.dataset.rejected}_duplicates_{service.dataset.duplicates}",
                }
            )
        )
        if settings.warm_cache:
            for row in scenarios():
                await service.recommend(RecommendRequest.model_validate(row["request"]), force_no_ai=True)
        yield
        service.cache.entries.clear()

    app = FastAPI(title="Серуен API", version="0.1.0", lifespan=lifespan)
    register_features(app)
    register_experiences(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def private_logs(request, call_next):
        started = time.perf_counter()
        request.state.mode, request.state.candidates, request.state.error = "none", 0, "none"
        try:
            response = await call_next(request)
        except Exception:
            # Never log request body, URL, validation input, provider content or exception text.
            request.state.error = "internal_error"
            response = JSONResponse(status_code=500, content={"error": {"code": "internal_error"}})
        if response.status_code >= 400 and request.state.error == "none":
            request.state.error = f"http_{response.status_code}"
        logger.info(
            json.dumps(
                {
                    "mode": request.state.mode,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "candidates": request.state.candidates,
                    "error_code": request.state.error,
                }
            )
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse(
            status_code=422,
            content={
                "error": {"code": "invalid_request", "fields": [".".join(map(str, e["loc"])) for e in exc.errors()]}
            },
        )

    @app.get("/health", response_model=Health)
    def health(request: Request):
        service = request.app.state.service
        return Health(
            mode_available=["no_ai", "ai"] if settings.gemini_api_key and not settings.mock else ["no_ai"],
            data_snapshot_date=service.dataset.snapshot_date,
            poi_count=len(service.dataset.pois),
            data_kind=settings.data_kind,
            retrieval_mode=service.retriever.mode,
            mock=settings.mock,
            google_places={
                "configured": bool(settings.google_places_api_key),
                "details_enabled": settings.google_places_enabled and not settings.mock,
                "ids_probe": request.app.state.places.probe_status,
            },
            twogis={
                "configured": bool(settings.twogis_api_key),
                "enabled": settings.twogis_enabled and not settings.mock,
                "last_status": request.app.state.twogis.last_status,
                "search_enabled": request.app.state.discovery.active(),
            },
        )

    @app.post("/recommend", response_model=RecommendResponse)
    async def recommend(payload: RecommendRequest, request: Request):
        example = payload.preferences.atmosphere_example_id
        if example and not any(r.example_id == example for r in request.app.state.service.features.examples(
                datetime.now(ALMATY).date())):
            raise PlanError("atmosphere_example_unavailable", 404)
        discovery = request.app.state.discovery
        if payload.source == "2gis" or (payload.source == "auto" and discovery.active()):
            response, error = await discovery.recommend(payload)
        else:
            response, error = await request.app.state.service.recommend(payload)
        request.state.mode, request.state.candidates, request.state.error = (
            response.mode,
            response.considered.candidates_found,
            error,
        )
        response.request_id = payload.request_id
        return response

    @app.get("/places/{poi_id}/details", response_model=PlaceDetails)
    async def place_details(poi_id: str, request: Request, lang: Literal["ru", "kk", "en"] = "ru"):
        try:
            return await request.app.state.places.details(poi_id, lang)
        except PlacesError as exc:
            request.state.error = exc.code
            return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code}})

    @app.get("/places/{poi_id}/2gis", response_model=TwoGisDetails)
    async def twogis_details(poi_id: str, request: Request, lang: Literal["ru", "kk", "en"] = "ru"):
        request.state.mode = "twogis"
        try:
            if poi_id.startswith("2gis_"):
                return await request.app.state.discovery.details(poi_id, lang)
            return await request.app.state.twogis.details(poi_id, lang)
        except PlacesError as exc:
            request.state.error = exc.code
            return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code}})

    @app.post("/places/{poi_id}/photos", response_model=PlacePhotos)
    async def place_photos(poi_id: str, payload: PhotoRequest, request: Request):
        # POST: the request text stays out of URLs and logs
        request.state.mode = "photos"
        try:
            return await request.app.state.photos.details(poi_id, payload)
        except PlacesError as exc:
            request.state.error = exc.code
            return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code}})

    @app.get("/scenarios")
    def get_scenarios(request: Request):
        return [{**row, "data_kind": request.app.state.service.settings.data_kind} for row in scenarios()]

    @app.post("/candidates")
    async def candidates_post(payload: RecommendRequest, request: Request):
        example = payload.preferences.atmosphere_example_id
        if example and not any(r.example_id == example for r in request.app.state.service.features.examples(
                datetime.now(ALMATY).date())):
            raise PlanError("atmosphere_example_unavailable", 404)
        if payload.source == "2gis" or (payload.source == "auto" and request.app.state.discovery.active()):
            response = await recommend(payload, request)
            return {"candidates": response.candidates, "excluded": response.excluded,
                    "radius_m": response.considered.radius_m, "radius_expanded": response.considered.radius_expanded,
                    "time_budget_min": response.considered.time_budget_min,
                    "target_time": response.considered.target_time, "retrieval_mode": "2gis",
                    "source": response.source, "source_error": response.source_error,
                    "next_cursor": response.next_cursor, "data_kind": "real"}
        intent, now, search = request.app.state.service.inspect(payload)
        request.state.mode, request.state.candidates = "no_ai", search.found
        return {
            "candidates": [h.candidate.model_dump() for h in search.hits],
            "excluded": [c.model_dump() for c in search.excluded],
            "radius_m": int(search.radius),
            "radius_expanded": search.expanded,
            "time_budget_min": intent.time_budget_min,
            "target_time": now.isoformat(),
            "retrieval_mode": search.mode,
            "data_kind": settings.data_kind,
        }

    @app.get("/candidates")
    async def candidates_get(
        request: Request,
        lat: float,
        lon: float,
        query: str = "",
        time_budget_min: int | None = None,
        companions: Literal["alone", "child", "group"] = "alone",
        now: datetime | None = None,
        lang: Literal["ru", "kk", "en", "auto"] = "auto",
        accessibility: bool = False,
        simulate: bool = False,
        exclude_categories: Annotated[list[str] | None, Query()] = None,
        precision_m: int = 100,
        source: Literal["gps", "map", "preset"] = "preset",
        mode: Literal["walk"] = "walk",
        temp_c: float | None = None,
        wind_ms: float | None = None,
        precip_mm: float = 0,
    ):
        try:
            weather = (
                Weather(temp_c=temp_c, wind_ms=wind_ms, precip_mm=precip_mm)
                if temp_c is not None or wind_ms is not None
                else None
            )
            payload = RecommendRequest(
                location=Location(lat=lat, lon=lon, precision_m=precision_m, source=source),
                query=query,
                context=Context(
                    time_budget_min=time_budget_min,
                    companions=companions,
                    now=now,
                    lang=lang,
                    accessibility=accessibility,
                    simulate=simulate,
                    exclude_categories=exclude_categories or [],
                    weather=weather,
                    mode=mode,
                ),
            )
        except ValidationError:
            return JSONResponse(status_code=422, content={"error": {"code": "invalid_request"}})
        return await candidates_post(payload, request)

    return app


app = create_app()

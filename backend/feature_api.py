"""Additive v1 endpoints. No accounts, wallet, rewards or server-side movement history."""

from datetime import datetime

from fastapi import Request
from fastapi.responses import JSONResponse

from .geo import ALMATY
from .places import PlacesError
from .plan_models import (ComfortRequest, ComfortView, IdentityRequest, OfflinePlan, OfflineRefreshRequest,
                          OfflineRequest, PlanRequest, PlanResponse, ReplanRequest)
from .plans import PlanError


def register_features(app):
    @app.exception_handler(PlanError)
    async def plan_error(request: Request, exc: PlanError):
        request.state.error = exc.code
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code}})

    async def run(request, method, payload):
        request.state.mode = "plan"
        try:
            result = await getattr(request.app.state.planner, method)(payload)
        except PlacesError as exc:
            raise PlanError(exc.code, exc.status) from None
        request.state.candidates = len(getattr(result, "stops", []))
        return result

    @app.post("/plans/build", response_model=PlanResponse)
    async def build_plan(payload: PlanRequest, request: Request):
        return await run(request, "build", payload)

    @app.post("/plans/recalculate", response_model=PlanResponse)
    async def recalculate_plan(payload: ReplanRequest, request: Request):
        return await run(request, "replan", payload)

    @app.post("/plans/export", response_model=OfflinePlan)
    async def export_plan(payload: OfflineRequest, request: Request):
        return await run(request, "export", payload)

    @app.post("/plans/refresh", response_model=PlanResponse)
    async def refresh_plan(payload: OfflineRefreshRequest, request: Request):
        return await run(request, "refresh", payload)

    @app.post("/comfort/search", response_model=list[ComfortView])
    async def comfort_search(payload: ComfortRequest, request: Request):
        request.state.mode = "comfort"
        return request.app.state.planner.comfort(payload)

    @app.get("/atmosphere/examples")
    async def atmosphere_examples(request: Request):
        rows = request.app.state.service.features.examples(datetime.now(ALMATY).date())
        return {"schema_version": 1, "status": "ready" if rows else "awaiting_data", "examples": [
            {"example_id": r.example_id, "poi_id": r.poi_id, "title": r.title, "titles": r.titles, "features": r.features,
             "photos": [p.model_dump(mode="json") for p in r.photos],
             "analysis_source": r.analysis_source, "analysis_version": r.analysis_version,
             "evidence": r.evidence.model_dump(mode="json")} for r in rows]}

    @app.get("/atmosphere/profiles")
    async def atmosphere_profiles(request: Request):
        from .atmosphere import PROFILES
        data = request.app.state.service.features
        today = datetime.now(ALMATY).date()
        profiles = []
        for ident, profile in PROFILES.items():
            # Examples illustrate this mood; they are not promises about every search result.
            rows, seen = [], set()
            for row in data.examples(today):
                poi = data.pois[data.canonical(row.poi_id)]
                if poi.category not in profile["categories"] or row.poi_id in seen:
                    continue
                match = data.match(row.poi_id, None, today, ident)
                if match.status != "confirmed":
                    continue
                seen.add(row.poi_id)
                photo = next((p for r in data.examples(today) for p in r.photos if p.photo_id in match.photo_ids), None)
                if photo:
                    rows.append({"poi_id": row.poi_id, "name": poi.name, "photo_url": str(photo.url),
                                 "attribution": photo.attribution, "features": match.matched_features,
                                 "checked_at": str(match.checked_at)})
            profiles.append({"id": ident, **profile, "examples": rows[:3], "reviewed_places": len(rows)})
        return {"schema_version": 1, "profiles": profiles}

    @app.post("/places/identities")
    async def identities(payload: IdentityRequest, request: Request):
        features = request.app.state.service.features
        return {"schema_version": 1, "identities": [
            {"poi_id": pid, "canonical_id": features.canonical(pid),
             "verified_link": pid in features.identities} for pid in dict.fromkeys(payload.poi_ids)]}

    @app.get("/features/status")
    async def feature_status(request: Request):
        service = request.app.state.service
        data = service.features
        today = datetime.now(ALMATY).date()
        return {"schema_version": 1, "gamification": False, "server_history": False,
                "routing_enabled": service.settings.routing_enabled,
                "data": {"comfort_points": len(data.comfort), "visit_conditions": len(data.conditions),
                         "atmosphere_examples": len(data.examples(datetime.now(ALMATY).date())),
                         "licensed_places": len(data.owned)},
                "ready": {"comfort_points": sum(data.verified(r.evidence, today, 30) for r in data.comfort.values()),
                          "visit_conditions": sum(data.condition(pid, today).kind != "unknown" for pid in data.conditions),
                          "atmosphere_examples": len(data.examples(today)),
                          "offline_places": sum(data.can_export(pid, today) for pid in data.owned)},
                "identity_aliases": sum(pid != canonical for pid, canonical in data.identities.items()),
                "data_fingerprint": data.fingerprint,
                "endpoints": ["/plans/build", "/plans/recalculate", "/plans/export", "/plans/refresh",
                              "/comfort/search", "/atmosphere/examples", "/places/identities"]}

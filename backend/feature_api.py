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
                         "licensed_places": len(data.owned)},
                "ready": {"comfort_points": sum(data.verified(r.evidence, today, 30) for r in data.comfort.values()),
                          "visit_conditions": sum(data.condition(pid, today).kind != "unknown" for pid in data.conditions),
                          "offline_places": sum(data.can_export(pid, today) for pid in data.owned)},
                "identity_aliases": sum(pid != canonical for pid, canonical in data.identities.items()),
                "data_fingerprint": data.fingerprint,
                "endpoints": ["/plans/build", "/plans/recalculate", "/plans/export", "/plans/refresh",
                              "/comfort/search", "/places/identities"]}

"""City stories, fair meeting candidates and winter plans. Stateless, no new paid providers."""
import json
from datetime import timedelta
from typing import Literal

from fastapi import Request
from pydantic import Field, model_validator

from .config import ROOT
from .feature_data import apply_feedback
from .geo import haversine, in_astana, speed, target_time
from .hours import open_status
from .intent import rule_intent
from .plan_models import PlanRequest, PlanResponse
from .plans import PlanError
from .places import PlacesError
from .schemas import Coords, Lang, Location, Model, RecommendRequest


class HistoryRequest(Model):
    location: Location
    radius_m: int = Field(default=3000, ge=100, le=10000)
    lang: Lang = "ru"


class MeetRequest(Model):
    request: RecommendRequest
    second_location: Location
    max_walk_min: int = Field(default=30, ge=1, le=60)
    stay_min: int = Field(default=30, ge=10, le=120)

    @model_validator(mode="after")
    def no_unhandled_constraints(self):
        if self.request.cursor or self.request.end:
            raise ValueError("meeting_has_no_cursor_or_finish")
        return self


class WinterRequest(Model):
    plan: PlanRequest
    max_outdoor_min: Literal[5, 10, 15] = 10


def register_experiences(app):
    def stories_for(lang):
        stories = json.loads((ROOT / "data/city_stories.json").read_text(encoding="utf-8"))
        return [{**{k: v for k, v in s.items() if k != "translations"}, **s["translations"][lang]} for s in stories]

    @app.get("/city/stories")
    def story_catalog(lang: Lang = "ru"):
        return {"items": stories_for(lang), "coverage": "reviewed_object_matches", "generated_by_ai": False}

    @app.post("/city/history")
    def history(payload: HistoryRequest):
        if not in_astana(payload.location.lat, payload.location.lon):
            raise PlanError("outside_astana")
        stories = stories_for(payload.lang)
        result = []
        for story in stories:
            distance = round(haversine(payload.location.lat, payload.location.lon,
                                       story["coords"]["lat"], story["coords"]["lon"]))
            if distance <= payload.radius_m:
                result.append({**story, "distance_m": distance})
        return {"items": sorted(result, key=lambda p: (p["distance_m"], p["id"])),
                "coverage": "reviewed_object_matches", "total_stories": len(stories), "generated_by_ai": False}

    @app.post("/meet/search")
    async def meeting(payload: MeetRequest, request: Request):
        planner = request.app.state.planner
        req = apply_feedback(payload.request.model_copy(deep=True))
        a, b = req.location, payload.second_location
        if not all(in_astana(p.lat, p.lon) for p in (a, b)):
            raise PlanError("outside_astana")
        intent = rule_intent(req)
        if planner.service.refusal(req, intent):
            raise PlanError("meeting_request_refused")
        now = target_time(req, intent)
        pace = speed(req, intent, now)
        limit = min(payload.max_walk_min, req.preferences.max_walk_min or 60)
        reserve = planner.settings.airport_reserve_min if intent.before_flight else 5
        try:
            pool, source = await planner.pool(req, b)
        except PlacesError as exc:
            raise PlanError(exc.code, exc.status) from None
        candidates, seen = [], set()
        other_req = req.model_copy(update={"location": b})
        for poi in pool:
            canonical = planner.features.canonical(poi.poi_id)
            if canonical in seen:
                continue
            seen.add(canonical)
            point = Coords(lat=poi.lat, lon=poi.lon)
            # Deliberately compare both people using the SAME model, rather than mix an
            # OSRM distance for one with a straight-line fallback for the other.
            routes = [planner.router.estimate([p, point], pace) for p in (a, b)]
            minutes = [r.minutes[0] for r in routes]
            longest = max(minutes)
            if longest > limit or longest + payload.stay_min + reserve > intent.time_budget_min:
                continue
            meeting_at = now + timedelta(minutes=longest)
            end = meeting_at + timedelta(minutes=payload.stay_min)
            if any(planner.rejection(poi, r, intent, now + timedelta(minutes=m), end, m)
                   for r, m in zip((req, other_req), minutes)):
                continue
            candidates.append({"poi_id": poi.poi_id, "name": poi.name, "category": poi.category,
                               "coords": point.model_dump(), "walk_min": minutes,
                               "difference_min": abs(minutes[0]-minutes[1]), "max_walk_min": longest,
                               "meeting_at": meeting_at, "stay_min": payload.stay_min,
                               "open_status": open_status(poi, meeting_at),
                               "visit_condition": planner.features.condition(poi.poi_id, now.date()),
                               "paths": [r.geometry for r in routes], "sources": poi.sources})
        candidates.sort(key=lambda p: (p["max_walk_min"], p["difference_min"], sum(p["walk_min"]), p["poi_id"]))
        return {"status": "ok" if candidates else "no_matches", "items": candidates[:3],
                "ranking": "minimize_longest_walk_then_difference", "source": source,
                "routing_source": "distance_estimate", "includes_return": False,
                "warning_codes": ["estimated_walking_times", "check_crossings_and_hours", "no_return_trip"],
                "data_kind": planner.settings.data_kind}

    @app.post("/plans/winter", response_model=PlanResponse)
    async def winter(payload: WinterRequest, request: Request):
        plan = payload.plan.model_copy(deep=True)
        prefs = plan.request.preferences
        prefs.indoor_only = True
        prefs.winter_mode = True
        weather = plan.request.context.weather
        maximum = 5 if weather and (weather.temp_c <= -15 or weather.wind_ms >= 10) else payload.max_outdoor_min
        prefs.max_walk_min = min(prefs.max_walk_min or 120, maximum)
        result = await request.app.state.planner.build(plan)
        # An explicit destination must never vanish in an automatically softened winter plan.
        if plan.stop_ids and result.state.remaining_ids != plan.stop_ids:
            result.fits = False
            result.status = "impossible"
            result.warning_codes.append("winter_cannot_keep_all_stops")
        lang = rule_intent(plan.request).lang
        result.notes.insert(0, {
            "ru": f"Зимний режим: переходы до {prefs.max_walk_min} мин, остановки в помещении; темп 60 м/мин. Это предпочтение, не гарантия безопасности. Лёд, ветер между зданиями и возможность войти не проверены.",
            "en": f"Winter mode: legs up to {prefs.max_walk_min} min, indoor stops, pace 60 m/min. A preference, not a safety guarantee. Ice, wind between buildings and entry are unverified.",
            "kk": f"Қысқы режим: жаяу жол {prefs.max_walk_min} минутқа дейін, аялдамалар ғимарат ішінде, қарқын 60 м/мин. Бұл қауіпсіздік кепілі емес. Мұз, ғимараттар арасындағы жел және кіру мүмкіндігі тексерілмеген.",
        }[lang])
        if not weather:
            result.warning_codes.append("weather_unknown")
        return result

"""Regression: a family already at a mall, explicit finish, and advisory AI."""

import copy
from datetime import datetime
import httpx
import pytest
from pydantic import ValidationError
from backend.geo import ALMATY
from backend.loader import Dataset
from backend.retrieval import Retriever
from backend.routing import WalkingRouter
from backend.schemas import Coords, Draft, POI, RecommendRequest
from backend.intent import rule_intent
from test_feature_expansion import expanded as expanded, api as api, ASK, post, plan


def family_request(**updates):
    return RecommendRequest.model_validate(
        {
            "location": {"lat": 51.133, "lon": 71.404},
            "query": "С ребёнком есть час",
            "context": {
                "companions": "child",
                "time_budget_min": 60,
                "simulate": True,
                "now": "2026-10-19T14:00:00+05:00",
            },
            **updates,
        }
    )


def mall_pois():
    # Synthetic coordinates close to the mall, never evidence of its real floor plans.
    return [
        POI(
            poi_id=f"kids_{i}",
            name=f"SYNTHETIC Kids {i}",
            lat=51.133 + i * 0.0003,
            lon=71.404,
            category="kids",
            kid_friendly=True,
            indoor=True,
            sources=["synthetic"],
        )
        for i in range(1, 4)
    ]


@pytest.mark.parametrize("finish", ["place", "return", "destination"])
def test_nearby_mall_children_venues_fit_an_hour(service, finish):
    req = family_request(
        finish_mode=finish, **({"end": {"lat": 51.133, "lon": 71.404}} if finish == "destination" else {})
    )
    intent = rule_intent(req)
    result = Retriever(Dataset(mall_pois(), "synthetic", 0, 0), None).search(
        req, intent, datetime(2026, 10, 19, 14, tzinfo=ALMATY), diversify=False
    )
    assert len(result.hits) == 3 and not result.excluded
    cards = service.assemble(
        req, intent, datetime(2026, 10, 19, 14, tzinfo=ALMATY), result, [], "no_ai", "rules", "none"
    ).recommendations
    assert len(cards) == 3
    for card in cards:
        assert 1 <= card.walk_min <= 3 and card.time_to_spend_min == 25
        assert card.budget_breakdown.total_min <= 36
        assert card.budget_breakdown.reserve_min == 5
        if finish == "place":
            assert card.budget_breakdown.walk_to_end_min == card.budget_breakdown.walk_back_min == 0


def test_ai_cannot_reorder_or_shrink_visits_to_make_places_fit(service):
    req = family_request(finish_mode="place")
    intent = rule_intent(req)
    now = datetime(2026, 10, 19, 14, tzinfo=ALMATY)
    result = Retriever(Dataset(mall_pois(), "synthetic", 0, 0), None).search(req, intent, now, diversify=False)
    baseline = service.assemble(req, intent, now, result, [], "no_ai", "rules", "none")
    selected = [
        Draft(poi_id=h.poi.poi_id, why="Тест", what_to_do="Тест", time_to_spend_min=1) for h in reversed(result.hits)
    ]
    ai = service.assemble(req, intent, now, result, selected, "ai", "rules", "none", set(d.poi_id for d in selected))
    assert [(r.poi_id, r.budget_breakdown) for r in ai.recommendations] == [
        (r.poi_id, r.budget_breakdown) for r in baseline.recommendations
    ]
    assert all(r.ai_reviewed and r.selection_source == "rules" for r in ai.recommendations)


def test_staying_does_not_charge_return_and_custom_finish_is_not_ignored(service):
    req = family_request(finish_mode="place")
    intent = rule_intent(req)
    now = datetime(2026, 10, 19, 14, tzinfo=ALMATY)
    retriever = Retriever(Dataset(mall_pois(), "synthetic", 0, 0), None)
    assert retriever.search(req, intent, now).hits
    req = family_request(finish_mode="destination", end={"lat": 51.20, "lon": 71.55})
    result = retriever.search(req, intent, now)
    assert not result.hits and all(c.excluded_because == "over_budget" for c in result.excluded)


@pytest.mark.parametrize(
    "fields",
    [
        {"finish_mode": "destination"},
        {"finish_mode": "place", "end": {"lat": 51.13, "lon": 71.4}},
        {"finish_mode": "return", "end": {"lat": 51.13, "lon": 71.4}},
    ],
)
def test_incoherent_finish_rejected(fields):
    with pytest.raises(ValidationError):
        family_request(**fields)


async def test_duplicate_indoor_finish_does_not_charge_snap_offsets(settings):
    settings.routing_enabled = True
    points = [Coords(lat=51.133, lon=71.404), Coords(lat=51.1333, lon=71.404), Coords(lat=51.1333, lon=71.404)]
    waypoints = [{"location": [p.lon + 0.0005, p.lat]} for p in points]

    def response(_):
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "waypoints": waypoints,
                "routes": [
                    {
                        "legs": [{"distance": 100}, {"distance": 0}],
                        "geometry": {"coordinates": [w["location"] for w in waypoints]},
                    }
                ],
            },
        )

    result = await WalkingRouter(settings, httpx.MockTransport(response)).route(points, 60)
    assert result.source == "osrm_foot" and result.distances[0] >= 100
    assert result.distances[-1] == result.minutes[-1] == 0


# The exact public venue ID survives a rounded private finish and subsequent replans.


def test_public_finish_resolves_exact_venue_without_a_phantom_last_leg(api):
    poi = api.app.state.service.features.owned["team_coffee"].poi
    poi.lat += 0.000123
    req = copy.deepcopy(ASK)
    req["location"] = {"lat": poi.lat, "lon": poi.lon}
    result = post(
        api,
        "/plans/build",
        plan(
            request=req,
            stop_ids=["team_coffee"],
            max_stops=1,
            finish_mode="destination",
            destination={"lat": poi.lat, "lon": poi.lon},
            finish_poi_id="team_coffee",
        ),
    )
    assert result["fits"] and result["legs"][-1]["walk_min"] == 0
    assert result["state"]["finish"]["lat"] == poi.lat
    assert result["state"]["finish_poi_id"] == "team_coffee"
    assert result["routing_source"] == "distance_estimate"
    assert result["routing_error"] == "nearby_indoor_estimate"
    assert any("этаж" in note for note in result["notes"])
    refreshed = post(
        api,
        "/plans/recalculate",
        {"request": req, "previous": result["state"], "reason": "refresh", "remaining_time_min": 90},
    )
    assert refreshed["state"]["finish"]["lat"] == poi.lat and refreshed["legs"][-1]["walk_min"] == 0

import copy
import json
from urllib.parse import urlparse

import pytest

from backend.config import ROOT
from test_feature_expansion import ASK, plan, post
from test_feature_expansion import api as api, expanded as expanded


def meeting(**changes):
    return {"request": copy.deepcopy(ASK), "second_location": {"lat": 51.132, "lon": 71.430}, **changes}


@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_history_is_curated_localized_and_wikipedia_links_are_place_specific(api, lang):
    result = post(api, "/city/history", {"location": ASK["location"], "lang": lang})
    assert not result["generated_by_ai"] and len(result["items"]) >= 3
    assert [p["distance_m"] for p in result["items"]] == sorted(p["distance_m"] for p in result["items"])
    links = [p['wikipedia_url'] for p in result['items'] if p.get('wikipedia_url')]
    assert len(set(links)) == len(links)
    for p in result["items"]:
        assert p["title"] and p["story"] and p["look_for"] and p["checked_at"]
        if p.get("wikipedia_url"):
            assert urlparse(p["wikipedia_url"]).hostname in {"ru.wikipedia.org", "kk.wikipedia.org", "en.wikipedia.org"}
        assert p["source_url"].startswith("https://")
    assert api.post("/city/history", json={"location": {"lat": 40, "lon": 40}}).status_code == 422
    assert post(api, "/city/history", {"location": {"lat": 51.02, "lon": 71.45}, "radius_m": 100})["items"] == []
    catalog = api.get('/city/stories', params={'lang': lang}).json()
    assert len(catalog['items']) == result['total_stories'] == 26
    assert all(s['aliases'] for s in catalog['items'])


def test_story_coordinates_match_real_dataset():
    pois = {p["poi_id"]: p for p in json.loads((ROOT / "data/poi.json").read_text(encoding="utf-8"))}
    for story in json.loads((ROOT / "data/city_stories.json").read_text(encoding="utf-8")):
        assert story["coords"] == {k: pois[story["poi_id"]][k] for k in ("lat", "lon")}
        assert set(story["translations"]) == {"ru", "en", "kk"}


def test_meeting_ranks_minimax_then_fairness_and_returns_both_approximate_paths(api):
    data = post(api, "/meet/search", meeting())
    assert data["status"] == "ok" and data["routing_source"] == "distance_estimate"
    assert not data["includes_return"] and len(data["items"]) <= 3
    assert data["items"][0]["poi_id"] == "team_second"
    scores = [(p["max_walk_min"], p["difference_min"], sum(p["walk_min"]), p["poi_id"]) for p in data["items"]]
    assert scores == sorted(scores)
    for p in data["items"]:
        assert p["max_walk_min"] == max(p["walk_min"])
        assert p["difference_min"] == abs(p["walk_min"][0]-p["walk_min"][1])
        assert len(p["paths"]) == 2
        assert p["paths"][0][0] == [71.430, 51.128]
        assert p["paths"][1][0] == [71.430, 51.132]


def test_meeting_checks_constraints_for_second_person_and_does_not_relax_them(api):
    data = meeting()
    data["request"]["preferences"] = {"max_distance_m": 200, "expense_mode": "free_only"}
    assert post(api, "/meet/search", data)["items"] == []
    data["second_location"] = ASK["location"]
    result = post(api, "/meet/search", data)
    assert [p["poi_id"] for p in result["items"]] == ["team_coffee"]


def test_meeting_checks_hours_until_both_finish(api):
    planner = api.app.state.planner
    for pid in ["team_second", "team_coffee", "team_paid", "team_unknown"]:
        p = planner.local(pid)
        p.opening_hours_raw = "Mo-Su 15:00-15:03"
    data = meeting()
    data["request"]["preferences"] = {"expense_mode": "free_only"}
    result = post(api, "/meet/search", data)
    assert not result["items"]


@pytest.mark.parametrize("patch", [
    {"second_location": {"lat": 40, "lon": 45}},
    {"max_walk_min": 0}, {"stay_min": 200},
    {"second_location": {"lat": 51.13, "lon": 71.43, "name": "private"}},
])
def test_meeting_rejects_invalid_or_unhandled_input(api, patch):
    assert api.post("/meet/search", json=meeting(**patch)).status_code == 422


def test_meeting_rejects_unhandled_finish_and_respects_time_budget(api):
    data = meeting()
    data["request"]["end"] = ASK["location"]
    assert api.post("/meet/search", json=data).status_code == 422
    del data["request"]["end"]
    data["request"]["context"]["time_budget_min"] = 15
    assert post(api, "/meet/search", data)["status"] == "no_matches"


def test_meeting_provider_failure_is_honest_and_not_synthetic(api, monkeypatch):
    from backend.places import PlacesError
    async def fail(*args):
        raise PlacesError("twogis_unavailable", 503)
    monkeypatch.setattr(api.app.state.planner, "pool", fail)
    result = api.post("/meet/search", json=meeting())
    assert result.status_code == 503 and result.json()["error"]["code"] == "twogis_unavailable"


def test_winter_has_indoor_stops_limits_every_leg_and_does_not_invent_weather(api):
    data = {"plan": plan(), "max_outdoor_min": 5}
    result = post(api, "/plans/winter", data)
    assert result["fits"]
    assert result["applied_preferences"]["winter_mode"]
    assert result["applied_preferences"]["indoor_only"]
    assert "weather_unknown" in result["warning_codes"]
    assert all(p["walk_min"] <= 5 for p in result["legs"])
    assert all(api.app.state.planner.local(s["poi_id"]).indoor for s in result["stops"])
    assert "weather" not in data["plan"]["request"]["context"]


def test_winter_honors_existing_tighter_limit_and_weather(api):
    data = {"plan": plan(), "max_outdoor_min": 15}
    data["plan"]["request"]["context"]["weather"] = {"temp_c": -22, "wind_ms": 4}
    data["plan"]["request"]["preferences"] = {"max_walk_min": 3}
    result = post(api, "/plans/winter", data)
    assert result["applied_preferences"]["max_walk_min"] == 3
    assert "weather_unknown" not in result["warning_codes"]


def test_winter_cannot_silently_drop_chosen_destination_or_long_final_leg(api):
    result = post(api, "/plans/winter", {"plan": plan(stop_ids=["team_coffee", "team_park"])})
    assert not result["fits"] and result["status"] == "impossible"
    assert "winter_cannot_keep_all_stops" in result["warning_codes"]
    result = post(api, "/plans/winter", {"plan": plan(stop_ids=["team_coffee"], finish_mode="destination",
              destination={"lat": 51.150, "lon": 71.430}), "max_outdoor_min": 5})
    assert not result["fits"]
    assert result["state"]["finish"]["lat"] == 51.150


def test_winter_pace_is_used_in_mild_weather_and_survives_replan(api):
    data = plan()
    data["request"]["context"]["weather"] = {"temp_c": 14, "wind_ms": 3}
    result = post(api, "/plans/winter", {"plan": data})
    assert result["legs"][0]["walk_min"] == 3  # 145 m at 60 m/min, versus 2 at 75
    new = post(api, "/plans/recalculate", {"previous": result["state"], "request": data["request"],
               "reason": "refresh", "remaining_time_min": 90})
    assert new["applied_preferences"]["winter_mode"]

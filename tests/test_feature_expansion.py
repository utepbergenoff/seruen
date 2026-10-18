"""Synthetic fixtures only. Never publish these records as real venue facts."""

import copy
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.feature_data import FeatureData, MODELS
from backend.geo import ALMATY

TODAY = datetime.now(ALMATY).date()
NOW = f"{TODAY}T15:00:00+05:00"
ASK = {"location": {"lat": 51.128, "lon": 71.430}, "query": "Хочу кофе", "source": "local",
       "context": {"time_budget_min": 90, "now": NOW, "simulate": True, "lang": "ru"}}


def evidence(**changes):
    return {"source_url": "https://example.org/synthetic-evidence", "checked_at": str(TODAY),
            "verification": "verified", "method": "team_review", "note": "Synthetic test record", **changes}


def owned(pid, lat, **changes):
    poi = {"poi_id": pid, "name": "SYNTHETIC " + pid, "lat": lat, "lon": 71.430,
           "category": "coffee", "indoor": True, "kid_friendly": True, "wheelchair": "yes",
           "opening_hours_raw": "24/7", "hours_source": "osm", "last_checked": str(TODAY),
           "sources": ["synthetic-test"], **changes}
    return {"poi": poi, "evidence": evidence(), "offline_allowed": True,
            "license": "synthetic-test", "attribution": "TEST ONLY"}


@pytest.fixture
def expanded(settings, tmp_path):
    records = {
        "feature_pois.json": [owned("team_coffee", 51.129), owned("team_second", 51.130),
                              owned("team_paid", 51.131), owned("team_unknown", 51.132),
                              owned("team_park", 51.130, category="park", indoor=False)],
        "comfort_points.json": [{**owned("team_bench", 51.129, category="park", indoor=False),
                                 "kind": "bench", "access": "public", "floor": None}],
        "visit_conditions.json": [
            {"poi_id": "team_coffee", "kind": "free", "evidence": evidence()},
            {"poi_id": "team_second", "kind": "optional_purchase", "evidence": evidence()},
            {"poi_id": "team_paid", "kind": "paid", "evidence": evidence()},
        ],
        "poi_identity_links.json": [{"canonical_id": "team_coffee", "aliases": ["2gis_7000001"],
                                     "evidence": evidence()}],
        "atmosphere_catalog.json": [{"example_id": "bright-reference", "poi_id": "team_coffee",
            "title": "Synthetic bright room", "features": ["indoor", "natural_light", "visible_seating"],
            "analysis_source": "manual", "analysis_version": "test-v1", "evidence": evidence(),
            "photos": [{"photo_id": "photo-1", "url": "https://example.org/synthetic.jpg",
                        "content_sha256": "a" * 64, "license": "synthetic-test", "attribution": "TEST ONLY",
                        "offline_allowed": True}]}],
    }
    for name, rows in records.items():
        (tmp_path / name).write_text(json.dumps({"version": 1, "items": rows}))
    settings.feature_data_dir = tmp_path
    return settings


@pytest.fixture
def api(expanded):
    with TestClient(create_app(expanded)) as client:
        yield client


def plan(**changes):
    return {"request": copy.deepcopy(ASK), "stop_ids": ["team_coffee", "team_second"], **changes}


def post(client, path, payload):
    r = client.post(path, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_new_endpoints_and_empty_production_collections(client):
    status = client.get("/features/status").json()
    assert not status["gamification"] and not status["server_history"]
    assert client.get("/atmosphere/examples").json()["status"] == "awaiting_data"
    assert post(client, "/comfort/search", {"location": ASK["location"]}) == []
    assert client.post("/recommend", json={**ASK, "preferences": {
        "atmosphere_example_id": "nonexistent"}}).status_code == 404


@pytest.mark.parametrize("reason,field", [("different_place", "exclude_poi_ids"),
                                          ("already_visited", "visited_poi_ids")])
def test_feedback_never_discards_old_exclusions(api, reason, field):
    ask = {**ASK, "preferences": {field: [f"old-{i}" for i in range(200)]},
           "feedback": {"reason": reason, "poi_id": "team_coffee"}}
    assert api.post("/recommend", json=ask).status_code == 422
    ask["feedback"]["poi_id"] = "old-0"
    result = post(api, "/recommend", ask)
    assert len(result["applied_preferences"][field]) == 200


def test_malformed_state_category_is_422_not_server_error(api):
    state = post(api, "/plans/build", plan())["state"]
    state["exclude_categories"] = ["arbitrary-category"]
    response = api.post("/plans/recalculate", json={"request": ASK, "previous": state,
                                                   "reason": "less_time", "remaining_time_min": 45})
    assert response.status_code == 422


def test_final_leg_also_obeys_walk_limit(api):
    payload = plan(stop_ids=["team_coffee"], finish_mode="destination",
                   destination={"lat": 51.150, "lon": 71.430})
    payload["request"]["preferences"] = {"max_walk_min": 5}
    result = post(api, "/plans/build", payload)
    assert result["budget"]["total_min"] < 90
    assert not result["fits"] and result["status"] == "impossible"
    assert {"poi_id": "finish", "reason": "finish_walk_limit"} in result["exclusions"]


def test_oversized_saved_plan_is_422(api):
    saved = post(api, "/plans/export", {"plan": plan()})
    saved["stops"] = saved["stops"] * 4
    assert api.post("/plans/refresh", json={"request": ASK, "saved": saved}).status_code == 422


def test_same_photo_cannot_describe_different_places(expanded):
    path = expanded.feature_data_dir / "atmosphere_catalog.json"
    body = json.loads(path.read_text())
    other = copy.deepcopy(body["items"][0])
    other.update(example_id="different-reference", poi_id="team_second")
    other["photos"][0]["photo_id"] = "different-photo-id"
    body["items"].append(other)
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError, match="atmosphere_photo_multiple_places"):
        FeatureData(expanded.feature_data_dir)


async def test_ai_budget_reserves_capacity_and_cools_down(settings):
    from backend.ai_budget import AIBudget
    from backend.generate import AIError
    settings.ai_requests_per_minute = 3
    settings.ai_requests_per_day = 3
    settings.photo_ai_reserved_requests = 2
    budget = AIBudget(settings)
    await budget.acquire(optional=True)
    with pytest.raises(AIError, match="ai_local_limit"):
        await budget.acquire(optional=True)
    await budget.acquire()
    budget.rate_limited()
    with pytest.raises(AIError, match="provider_cooldown"):
        await budget.acquire()


def test_schema_export_and_invalid_data_fail_without_network(expanded, tmp_path):
    from scripts.validate_feature_data import write_schemas
    out = tmp_path / "schemas"
    write_schemas(out)
    for name in MODELS:
        schema = json.loads((out / name.replace(".json", ".schema.json")).read_text())
        assert schema["properties"]["version"]["const"] == 1
        assert schema["additionalProperties"] is False
    (expanded.feature_data_dir / "comfort_points.json").write_text('{"version": 2,"items":[]}')
    with pytest.raises(ValueError, match="feature_data_format"):
        FeatureData(expanded.feature_data_dir)


def test_round_trip_budget_and_arrival_times(api):
    result = post(api, "/plans/build", plan())
    assert result["status"] == "ok" and result["fits"]
    assert len(result["stops"]) == 2 and len(result["legs"]) == 3
    b = result["budget"]
    assert b["total_min"] == b["walking_min"] + b["visiting_min"] + b["reserve_min"] <= 90
    assert result["state"]["finish"] == result["state"]["origin"]
    first, second = result["stops"]
    assert datetime.fromisoformat(second["arrival_at"]) > datetime.fromisoformat(first["departure_at"])
    assert first["canonical_id"] == "team_coffee"


def test_destination_changes_last_leg_and_impossible_budget(api):
    result = post(api, "/plans/build", plan(finish_mode="destination", destination={"lat": 51.134, "lon": 71.430}))
    assert result["fits"] and result["state"]["finish"]["lat"] == 51.134
    p = plan(finish_mode="destination", destination={"lat": 51.25, "lon": 71.65})
    p["request"]["context"]["time_budget_min"] = 10
    result = post(api, "/plans/build", p)
    assert result["status"] == "impossible" and not result["fits"]
    assert "do_not_start_plan" in result["warning_codes"]


def test_replan_preserves_original_finish_completion_and_filters(api):
    p = plan()
    p["request"]["preferences"] = {"expense_mode": "no_required_purchase"}
    old = post(api, "/plans/build", p)
    req = copy.deepcopy(ASK)
    req["location"] = {"lat": 51.129, "lon": 71.430}
    new = post(api, "/plans/recalculate", {"request": req, "previous": old["state"],
        "reason": "less_time", "remaining_time_min": 40, "completed_ids": ["team_coffee"]})
    assert new["state"]["finish"] == old["state"]["origin"]
    assert new["state"]["completed_ids"] == ["team_coffee"]
    assert all(p["poi_id"] != "team_coffee" for p in new["stops"])
    assert new["budget"]["available_min"] == 40
    assert new["applied_preferences"]["expense_mode"] == "no_required_purchase"


@pytest.mark.parametrize("reason", ["closed", "busy", "skip"])
def test_replan_rejects_skipped_place(api, reason):
    old = post(api, "/plans/build", plan())
    new = post(api, "/plans/recalculate", {"request": ASK, "previous": old["state"], "reason": reason,
        "remaining_time_min": 60, "poi_id": "team_coffee"})
    assert "team_coffee" in new["state"]["skipped_ids"]
    assert all(p["canonical_id"] != "team_coffee" for p in new["stops"])


def test_replan_cold_and_tired(api):
    old = post(api, "/plans/build", plan())
    for reason in ("cold", "tired"):
        new = post(api, "/plans/recalculate", {"request": ASK, "previous": old["state"], "reason": reason,
            "remaining_time_min": 60})
        assert new["applied_preferences"]["max_walk_min"] == 5
        if reason == "cold":
            assert new["applied_preferences"]["indoor_only"]
            assert all(p["category"] != "park" for p in new["stops"])


def test_invalid_stale_or_forged_plan_input(api):
    assert api.post("/plans/build", json=plan(stop_ids=["invented"])).status_code == 404
    assert api.post("/plans/build", json=plan(stop_ids=["team_coffee", "team_coffee"])).status_code == 422
    assert api.post("/plans/build", json=plan(finish_mode="destination")).status_code == 422
    forged = plan()
    forged["minutes"] = 1
    assert api.post("/plans/build", json=forged).status_code == 422
    old = post(api, "/plans/build", plan())["state"]
    old["created_at"] = (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    assert api.post("/plans/recalculate", json={"request": ASK, "previous": old,
        "reason": "less_time", "remaining_time_min": 30}).status_code == 409


def test_hours_at_arrival_and_closing_during_visit(api):
    data = api.app.state.service.features
    coffee = data.pois["team_coffee"]
    # Open at the initial time, closes before a complete 20-minute visit.
    data.pois["team_coffee"] = coffee.model_copy(update={"opening_hours_raw": "15:00-15:10"})
    result = post(api, "/plans/build", plan(stop_ids=["team_coffee"]))
    assert not result["stops"]
    assert any(x["reason"] == "closed_at_visit" for x in result["exclusions"])
    data.pois["team_coffee"] = coffee.model_copy(update={"opening_hours_raw": "unsupported schedule"})
    result = post(api, "/plans/build", plan(stop_ids=["team_coffee"]))
    assert result["stops"][0]["open_status"]["state"] == "unknown"


def test_feedback_exclusion_undo_and_aliases(api):
    ask = {**ASK, "preferences": {"expense_mode": "free_only"}}
    before = post(api, "/recommend", ask)
    assert [p["poi_id"] for p in before["recommendations"]] == ["team_coffee"]
    after = post(api, "/recommend", {**ask, "feedback": {"reason": "different_place", "poi_id": "2gis_7000001"}})
    assert not after["recommendations"] and "restore_excluded_places" in after["relaxation_options"]
    undo = post(api, "/recommend", ask)
    assert undo["recommendations"]
    ids = post(api, "/places/identities", {"poi_ids": ["2gis_7000001", "team_coffee", "unlinked"]})
    assert ids["identities"][0]["canonical_id"] == "team_coffee"
    assert ids["identities"][2]["verified_link"] is False


@pytest.mark.parametrize("preferences,expected", [
    ({"expense_mode": "free_only"}, {"team_coffee"}),
    ({"expense_mode": "no_required_purchase"}, {"team_coffee", "team_second"}),
    ({"expense_mode": "free_only", "exclude_visited": True, "visited_poi_ids": ["2gis_7000001"]}, set()),
])
def test_expense_and_history_filters(api, preferences, expected):
    result = post(api, "/recommend", {**ASK, "preferences": preferences})
    assert {p["poi_id"] for p in result["recommendations"]} == expected


def test_stale_or_conflicting_price_is_unknown(api):
    data = api.app.state.service.features
    condition = data.conditions["team_coffee"]
    condition.evidence.checked_at = TODAY-timedelta(days=31)
    assert data.condition("team_coffee", TODAY).kind == "unknown"
    result = post(api, "/recommend", {**ASK, "preferences": {"expense_mode": "free_only"}})
    assert not result["recommendations"]


def test_wrong_type_needs_category_and_too_far_is_applied(api):
    assert api.post("/recommend", json={**ASK, "feedback": {"reason": "wrong_type"}}).status_code == 422
    result = post(api, "/recommend", {**ASK, "feedback": {"reason": "too_far", "max_walk_min": 1}})
    assert result["applied_preferences"]["max_walk_min"] == 1
    assert all(p["walk_min"] <= 1 for p in result["recommendations"])
    result = post(api, "/recommend", {**ASK, "feedback": {"reason": "wrong_type", "category": "coffee"}})
    assert all(p["category"] != "coffee" for p in result["recommendations"])


def test_comfort_distance_to_segment_and_verified_public_filter(api):
    result = post(api, "/comfort/search", {"location": ASK["location"], "radius_m": 50,
        "route_points": [{"lat": 51.129, "lon": 71.425}, {"lat": 51.129, "lon": 71.435}]})
    assert result[0]["poi_id"] == "team_bench" and result[0]["distance_to_route_m"] == 0
    api.app.state.service.features.comfort["team_bench"].access = "customers_only"
    assert post(api, "/comfort/search", {"location": ASK["location"], "public_only": True}) == []
    api.app.state.service.features.comfort["team_bench"].evidence.verification = "unverified"
    assert post(api, "/comfort/search", {"location": ASK["location"]}) == []


def test_add_comfort_stop_recalculates_budget(api):
    old = post(api, "/plans/build", plan(stop_ids=["team_coffee"]))
    new = post(api, "/plans/recalculate", {"request": ASK, "previous": old["state"], "reason": "add_stop",
        "remaining_time_min": 90, "poi_id": "team_bench"})
    assert {p["poi_id"] for p in new["stops"]} == {"team_coffee", "team_bench"}
    assert new["budget"]["total_min"] > old["budget"]["total_min"]


def test_atmosphere_precomputed_features_work_without_ai(api):
    examples = api.get("/atmosphere/examples").json()
    assert examples["status"] == "ready" and examples["examples"][0]["analysis_source"] == "manual"
    result = post(api, "/recommend", {**ASK, "preferences": {"atmosphere_example_id": "bright-reference"}})
    assert [p["poi_id"] for p in result["recommendations"]] == ["team_coffee"]
    match = result["recommendations"][0]["atmosphere_match"]
    assert match["source"] == "manual" and match["matched_features"] == ["natural_light", "visible_seating"]
    assert result["mode"] == "no_ai"


def test_export_only_licensed_facts_and_refresh_ignores_forged_names(api):
    result = post(api, "/plans/export", {"plan": plan()})
    assert result["status"] == "saved" and result["contains_full_route"]
    assert all(p["license"] == "synthetic-test" for p in result["stops"])
    assert "photos" not in result["stops"][0] and "visit_condition" not in result["stops"][0]
    result["stops"][0]["name"] = "FORGED NAME"
    result["stops"][0]["coords"] = {"lat": 51.20, "lon": 71.6}
    refreshed = post(api, "/plans/refresh", {"saved": result, "request": ASK})
    assert refreshed["stops"][0]["name"] == "SYNTHETIC team_coffee"
    assert refreshed["stops"][0]["coords"]["lat"] == 51.129
    result["schema_version"] = 2
    assert api.post("/plans/refresh", json={"saved": result, "request": ASK}).status_code == 422


def test_partial_export_never_keeps_misleading_full_route(api):
    api.app.state.service.features.owned["team_second"].offline_allowed = False
    result = post(api, "/plans/export", {"plan": plan()})
    assert result["status"] == "saved" and not result["contains_full_route"]
    assert result["omitted_ids"] == ["team_second"]
    assert result["budget"] is None and result["origin"] is None
    assert [s["poi_id"] for s in result["stops"]] == ["team_coffee"]


def test_deny_unknown_offline_rights_and_impossible_plan(api):
    for record in api.app.state.service.features.owned.values():
        record.offline_allowed = False
    result = post(api, "/plans/export", {"plan": plan()})
    assert result["status"] == "not_exportable" and not result["stops"]
    impossible = plan(finish_mode="destination", destination={"lat": 51.25, "lon": 71.65})
    impossible["request"]["context"]["time_budget_min"] = 5
    assert post(api, "/plans/export", {"plan": impossible})["status"] == "revalidation_failed"


def test_invalid_data_rejected_and_schemas_have_all_collections(expanded):
    assert len(MODELS) == 5
    path = expanded.feature_data_dir / "poi_identity_links.json"
    body = json.loads(path.read_text())
    body["items"].append(body["items"][0])
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError, match="identity_overlap"):
        FeatureData(expanded.feature_data_dir)


def test_street_routing_uses_distance_and_personal_pace(expanded):
    expanded.routing_enabled = True
    seen = []
    def respond(r):
        seen.append(r)
        points = [[float(v) for v in pair.split(",")] for pair in r.url.path.rsplit("/", 1)[1].split(";")]
        return httpx.Response(200, json={"code": "Ok", "waypoints": [{"location": p} for p in points],
            "routes": [{"legs": [{"distance": 300, "duration": 1} for _ in points[1:]],
                        "geometry": {"coordinates": points}}]})
    with TestClient(create_app(expanded, routing_transport=httpx.MockTransport(respond))) as c:
        result = post(c, "/plans/build", plan(stop_ids=["team_coffee"]))
        assert result["routing_source"] == "osrm_foot"
        assert result["budget"]["walking_min"] == 8  # 600 m / 75, not provider's 2 seconds
        assert len(seen) == 1 and "routed-foot" in seen[0].url.path


@pytest.mark.parametrize("body", [{"code": "NoRoute"}, {"code": "Ok", "routes": []}])
def test_bad_routing_response_is_labelled_estimate(expanded, body):
    expanded.routing_enabled = True
    with TestClient(create_app(expanded, routing_transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)))) as c:
        result = post(c, "/plans/build", plan())
        assert result["routing_source"] == "distance_estimate" and result["routing_error"] == "routing_unavailable"


def test_feature_request_privacy(api, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="seruen")
    ask = copy.deepcopy(ASK)
    ask["query"] = "private-feature-query кофе"
    ask["location"] = {"lat": 51.12812345, "lon": 71.43012345}
    post(api, "/plans/build", plan(request=ask))
    messages = [r.message for r in caplog.records if r.name == "seruen"]
    assert messages and all("private-feature" not in m and "51.128" not in m for m in messages)


def test_catalog_filter_and_aliases_apply_before_ai(expanded):
    expanded.twogis_enabled = True
    expanded.twogis_api_key = "test-only"
    body = {"meta": {"code": 200}, "result": {"total": 1, "items": [{
        "id": "7000001", "name": "SYNTHETIC remote", "type": "branch", "point": {"lat": 51.129, "lon": 71.430},
        "rubrics": [{"name": "Кофейни"}]}]}}
    with TestClient(create_app(expanded, twogis_transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)))) as c:
        req = {**ASK, "source": "2gis", "preferences": {"visited_poi_ids": ["team_coffee"], "exclude_visited": True}}
        result = post(c, "/recommend", req)
        assert not result["recommendations"] and not result["nearby_places"]
        assert any(p["excluded_because"] == "already_visited" for p in result["excluded"])
        # Same provider ID resolves via the prepared identity map for strict free filtering.
        result = post(c, "/recommend", {**ASK, "source": "2gis", "preferences": {"expense_mode": "free_only"}})
        assert result["recommendations"][0]["canonical_id"] == "team_coffee"


@pytest.mark.parametrize('reason', ['cold', 'tired'])
def test_empty_replan_is_not_a_successful_replacement(api, reason):
    old = post(api, '/plans/build', plan())
    previous = copy.deepcopy(old['state'])
    request = copy.deepcopy(ASK)
    request['preferences'] = {'exclude_poi_ids': list(api.app.state.service.features.pois)}
    response = api.post('/plans/recalculate', json={'request': request, 'previous': previous,
        'reason': reason, 'remaining_time_min': 60})
    assert response.status_code == 409
    assert response.json() == {'error': {'code': 'no_replacement_found'}}
    assert previous == old['state'] and old['stops']


def test_build_selected_destination_does_not_substitute_first_recommendation(api):
    result = post(api, '/plans/build', plan(stop_ids=['team_second'], max_stops=1))
    assert result['fits'] and result['status'] == 'ok'
    assert [s['poi_id'] for s in result['stops']] == ['team_second']
    assert result['legs'][0]['to_id'] == 'team_second'
    assert result['state']['remaining_ids'] == ['team_second']


@pytest.mark.parametrize('reason', ['cold', 'tired'])
def test_nearby_break_preserves_all_stops_and_original_finish(api, reason):
    places = api.app.state.service.features.pois
    places['team_pause'] = places['team_coffee'].model_copy(update={'poi_id': 'team_pause', 'lat': 51.1283})
    old = post(api, '/plans/build', plan(request={**ASK, 'context': {**ASK['context'], 'time_budget_min': 150}}))
    previous = copy.deepcopy(old['state'])
    new = post(api, '/plans/recalculate', {'request': ASK, 'previous': previous,
        'reason': reason, 'remaining_time_min': 150, 'keep_stops': True})
    assert new['fits']
    assert [s['poi_id'] for s in new['stops']][1:] == previous['remaining_ids']
    assert new['stops'][0]['poi_id'] not in previous['remaining_ids']
    if reason == 'cold':
        assert places[new['stops'][0]['poi_id']].indoor
    else:
        assert new['stops'][0]['poi_id'] == 'team_bench'
    assert new['state']['finish'] == previous['finish']
    assert new['state']['finish_mode'] == previous['finish_mode']
    assert new['legs'][0]['walk_min'] <= 5
    assert new['applied_preferences'] == previous['preferences']
    assert previous == old['state']


def test_nearby_break_cannot_trade_away_destination_to_fit_budget(api):
    places = api.app.state.service.features.pois
    places['team_pause'] = places['team_coffee'].model_copy(update={'poi_id': 'team_pause', 'lat': 51.1283})
    old = post(api, '/plans/build', plan())
    r = api.post('/plans/recalculate', json={'request': ASK, 'previous': old['state'],
        'reason': 'cold', 'remaining_time_min': old['budget']['total_min'], 'keep_stops': True})
    assert r.status_code == 409
    assert r.json()['error']['code'] == 'no_replacement_found'


def test_explicit_catalog_selection_changes_inferred_category_but_keeps_hard_filters(api):
    result = post(api, '/plans/build', plan(stop_ids=['team_park'], max_stops=1))
    assert [s['poi_id'] for s in result['stops']] == ['team_park']
    req = {**ASK, 'preferences': {'indoor_only': True}}
    result = post(api, '/plans/build', plan(request=req, stop_ids=['team_park'], max_stops=1))
    assert not result['stops']
    assert any(e['reason'] == 'indoor_required' for e in result['exclusions'])


def test_cold_break_keeps_a_distant_mall_destination_instead_of_replacing_it(api):
    places = api.app.state.service.features.pois
    places['team_mall'] = places['team_coffee'].model_copy(update={
        'poi_id': 'team_mall', 'lat': 51.136, 'category': 'shopping', 'name': 'SYNTHETIC MALL'})
    destination = {'lat': 51.136, 'lon': 71.430, 'source': 'map'}
    request = {**ASK, 'query': 'Хочу погулять в ТРЦ', 'context': {**ASK['context'], 'time_budget_min': 180}}
    old = post(api, '/plans/build', plan(request=request, stop_ids=['team_mall'],
        finish_mode='destination', destination=destination))
    assert old['fits'], {k: old[k] for k in ['status', 'exclusions', 'notes', 'budget']}
    assert old['legs'][0]['walk_min'] > 5
    new = post(api, '/plans/recalculate', {'request': request, 'previous': old['state'],
        'reason': 'cold', 'remaining_time_min': 180, 'keep_stops': True})
    assert new['fits'] and new['stops'][-1]['poi_id'] == 'team_mall'
    assert len(new['stops']) == 2 and new['legs'][0]['walk_min'] <= 5
    assert new['state']['finish'] == old['state']['finish']

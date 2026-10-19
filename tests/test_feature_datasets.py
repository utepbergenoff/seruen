"""Stream A data for F4-F8: the committed sets load against the real snapshot and stay honest."""

import json
from pathlib import Path

from backend.feature_data import FeatureData
from backend.loader import load_pois

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def items(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))["items"]


def test_committed_feature_sets_load_with_the_real_snapshot():
    features = FeatureData(DATA, load_pois(DATA / "poi.json").pois)
    assert len(features.comfort) == len(items("comfort_points.json"))
    assert len(features.conditions) == len(items("visit_conditions.json"))


def test_a_cafe_is_never_marked_free():
    pois = {p.poi_id: p for p in load_pois(DATA / "poi.json").pois}
    for row in items("visit_conditions.json"):
        poi = pois.get(row["poi_id"])
        is_cafe = (poi and poi.category in ("coffee", "food")) or "кофейн" in row["evidence"]["note"].lower()
        if is_cafe:
            assert row["kind"] != "free", row["poi_id"]


def test_only_a_field_visit_verifies_a_comfort_point():
    for row in items("comfort_points.json"):
        if row["evidence"]["verification"] == "verified":
            assert row["evidence"]["method"] == "field_visit", row["poi"]["poi_id"]




def test_october_field_visit_corrections_and_expiry():
    from datetime import date

    features = FeatureData(DATA, load_pois(DATA / 'poi.json').pois)
    assert 'team_comfort_drinkit_mega_toilet' not in features.comfort
    assert features.comfort['team_comfort_lrt_universitet_toilet'].access == 'paid'
    assert features.condition('2gis_70000001072135261', date(2026, 10, 19)).kind == 'optional_purchase'
    assert features.condition('osm_way_230401645', date(2026, 10, 19)).kind == 'paid'
    assert features.condition('osm_way_917478479', date(2026, 10, 19)).kind == 'unknown'
    assert features.condition('2gis_70000001072135261', date(2026, 11, 19)).kind == 'unknown'
    assert features.can_export('team_comfort_mega_warm', date(2026, 10, 19))


def test_public_comfort_search_excludes_paid_lrt_and_removed_toilet(monkeypatch):
    from datetime import datetime
    from fastapi.testclient import TestClient
    from backend.app import create_app
    from backend.config import Settings
    from backend.geo import ALMATY
    from backend import plans

    class FieldDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 19, 14, tzinfo=ALMATY)

    monkeypatch.setattr(plans, 'datetime', FieldDate)
    settings = Settings(poi_path=DATA / 'poi.json', feature_data_dir=DATA, warm_cache=False)
    with TestClient(create_app(settings)) as client:
        point = client.app.state.service.features.comfort['team_comfort_lrt_universitet_toilet'].poi
        ask = {'location': {'lat': point.lat, 'lon': point.lon}, 'radius_m': 2000}
        all_points = client.post('/comfort/search', json=ask).json()
        public = client.post('/comfort/search', json={**ask, 'public_only': True}).json()
        assert any(p['poi_id'] == point.poi_id and p['access'] == 'paid' for p in all_points)
        assert public and all(p['access'] == 'public' and p['verified'] for p in public)
        assert all(p['poi_id'] != point.poi_id for p in public)
        assert all(p['poi_id'] != 'team_comfort_drinkit_mega_toilet' for p in all_points)

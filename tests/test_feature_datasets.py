"""Stream A data for F4-F8: the committed sets load against the real snapshot and stay honest."""

import hashlib
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
    assert len(features.atmosphere) == len(items("atmosphere_catalog.json"))


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


def test_atmosphere_photo_hashes_match_the_hosted_files():
    prefix = "https://seruen-astana.netlify.app/img/places/"
    for row in items("atmosphere_catalog.json"):
        for photo in row["photos"]:
            if photo["url"].startswith(prefix):
                local = ROOT / "frontend/img/places" / photo["url"].removeprefix(prefix)
                assert hashlib.sha256(local.read_bytes()).hexdigest() == photo["content_sha256"], photo["photo_id"]

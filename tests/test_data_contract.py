"""Stream A <-> stream B contract: the committed snapshot loads in the backend with nothing rejected."""

import json
from pathlib import Path

from backend.loader import load_pois

ROOT = Path(__file__).resolve().parent.parent


def test_committed_poi_snapshot_loads_in_backend_without_rejections():
    path = ROOT / "data/poi.json"
    expected = len(json.loads(path.read_text(encoding="utf-8")))
    dataset = load_pois(path)
    assert dataset.rejected == 0
    assert dataset.duplicates == 0
    assert len(dataset.pois) == expected == 1251

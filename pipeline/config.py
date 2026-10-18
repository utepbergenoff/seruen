"""Shared paths and constants for the pipeline."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"
POI_PATH = DATA_DIR / "poi.json"
REPORT_PATH = DATA_DIR / "quality_report.md"

# Astana bounding box: south, west, north, east
BBOX = (51.00, 71.25, 51.25, 71.65)

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

USER_AGENT = "seruen-pipeline/0.1 (hackathon Build with AI; github.com/utepbergenoff/seruen)"


def latest_raw(prefix: str) -> Path:
    """Newest file in data/raw/ that starts with prefix (e.g. 'osm_')."""
    files = sorted(RAW_DIR.glob(f"{prefix}*.json"))
    if not files:
        raise FileNotFoundError(f"No {prefix}*.json in {RAW_DIR}; run the previous step first")
    return files[-1]

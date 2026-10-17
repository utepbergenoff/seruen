"""A1: collect POI from OpenStreetMap via Overpass -> data/raw/osm_YYYYMMDD.json.

Run: python -m pipeline.collect
"""

import json
import sys
import time
from datetime import datetime, timezone

import requests

from pipeline.config import BBOX, OVERPASS_SERVERS, RAW_DIR, USER_AGENT

RETRY_STATUSES = {429, 502, 503, 504}
MAX_ATTEMPTS = 3
PAUSE_S = 30


def build_query(bbox: tuple[float, float, float, float] = BBOX) -> str:
    b = ",".join(str(x) for x in bbox)
    return f"""[out:json][timeout:180];
(
  nwr["amenity"~"^(cafe|restaurant|library|theatre|cinema|ice_cream|food_court|coworking_space|bar|pub|nightclub|hookah_lounge|arts_centre|planetarium)$"]({b});
  nwr["office"="coworking"]({b});
  nwr["leisure"="escape_game"]({b});
  nwr["tourism"~"^(museum|attraction|viewpoint|gallery|artwork|zoo|aquarium|theme_park)$"]({b});
  nwr["leisure"~"^(park|garden|playground|nature_reserve|ice_rink|fitness_centre|sports_centre|water_park)$"]({b});
  nwr["shop"="mall"]({b});
  nwr["historic"]({b});
);
out center tags;"""


def fetch(query: str) -> dict:
    """POST the query, retrying on overload and falling back to the next server."""
    last_err: Exception | None = None
    for server in OVERPASS_SERVERS:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = requests.post(
                    server,
                    data={"data": query},
                    headers={"User-Agent": USER_AGENT},
                    timeout=240,
                )
                if resp.status_code in RETRY_STATUSES:
                    raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                resp.raise_for_status()
                print(f"[collect] ok from {server} (attempt {attempt})")
                return resp.json()
            except (requests.RequestException, ValueError) as err:
                last_err = err
                print(f"[collect] {server} attempt {attempt} failed: {err}", file=sys.stderr)
                if attempt < MAX_ATTEMPTS:
                    time.sleep(PAUSE_S)
    raise RuntimeError(f"All Overpass servers failed: {last_err}")


def main() -> None:
    now = datetime.now(timezone.utc)
    data = fetch(build_query())
    data["_meta"] = {"collected_at": now.isoformat(timespec="seconds"), "bbox": list(BBOX)}

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"osm_{now:%Y%m%d}.json"
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    elements = data.get("elements", [])
    named = sum(1 for e in elements if e.get("tags", {}).get("name"))
    print(f"[collect] {len(elements)} elements ({named} named) -> data/raw/{out.name}")


if __name__ == "__main__":
    main()

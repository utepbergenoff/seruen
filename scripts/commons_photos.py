"""Collect free (Wikimedia Commons) photos taken next to places from data/poi.json.

Writes frontend/img/places/index.json, the photo list the backend reads for /places/{id}/photos.
Only categories that are usually photographed from outside are searched: Commons has street views
next to cafes, not their interiors, so cafes get photos from the team instead (entries with
"source": "team" are kept as they are). Gemini later checks that a photo really shows the place.

    python scripts/commons_photos.py            # about 30 minutes, polite to the Commons API
    python scripts/commons_photos.py --by-name  # only add photos found by the place's name (named landmarks)
    python scripts/host_photos.py               # then copy them onto the website
"""
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend/img/places/index.json"
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "SeruenAstana/1.0 (hackathon walk assistant; https://seruen-astana.netlify.app)"}
RADIUS = {"park": 120, "viewpoint": 80, "culture": 70, "unusual": 70, "kids": 50, "shopping": 70, "sport": 70}
PER_PLACE = 5
IMAGE = re.compile(r"\.(jpe?g|png|webp)$", re.I)


def query(params, tries=6):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": 2})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == tries - 1:
                raise
            time.sleep(int(e.headers.get("Retry-After") or 0) or 10 * (attempt + 1))
    return {}


def text(meta, key):
    value = (meta.get(key) or {}).get("value", "")
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()[:120] or None


def photos_near(poi):
    data = query({"action": "query", "generator": "geosearch", "ggscoord": f"{poi['lat']}|{poi['lon']}",
                  "ggsradius": RADIUS[poi["category"]], "ggsnamespace": 6, "ggslimit": 15,
                  "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 800,
                  "iiextmetadatafilter": "Artist|LicenseShortName"})
    pages = sorted((data.get("query") or {}).get("pages", []), key=lambda p: p.get("index", 0))
    result = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        if not IMAGE.search(page.get("title", "")) or not info.get("thumburl"):
            continue
        meta = info.get("extmetadata") or {}
        result.append({"url": info["thumburl"], "page_url": info.get("descriptionurl"),
                       "author": text(meta, "Artist"), "license": text(meta, "LicenseShortName"),
                       "source": "commons"})
        if len(result) == PER_PLACE:
            break
    return result


def photos_by_name(poi):
    # the nearest photos often show the street next to a landmark; its name finds the landmark itself
    name = poi.get("name_en") or poi["name"]
    data = query({"action": "query", "generator": "search", "gsrsearch": f'"{name}" Astana filetype:bitmap',
                  "gsrnamespace": 6, "gsrlimit": 5, "prop": "imageinfo", "iiprop": "url|extmetadata",
                  "iiurlwidth": 800, "iiextmetadatafilter": "Artist|LicenseShortName"})
    pages = sorted((data.get("query") or {}).get("pages", []), key=lambda p: p.get("index", 0))
    result = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        if IMAGE.search(page.get("title", "")) and info.get("thumburl"):
            meta = info.get("extmetadata") or {}
            result.append({"url": info["thumburl"], "page_url": info.get("descriptionurl"),
                           "author": text(meta, "Artist"), "license": text(meta, "LicenseShortName"),
                           "source": "commons"})
    return result[:3]


def by_name():
    pois = [p for p in json.loads((ROOT / "data/poi.json").read_text())
            if p["category"] in RADIUS and not p.get("name_generic") and len(p["name"]) > 3]
    data = json.loads(OUT.read_text())
    places, added = data["places"], 0
    for poi in pois:
        try:
            found = photos_by_name(poi)
        except Exception as exc:
            print(f"skip {poi['poi_id']}: {exc}", file=sys.stderr)
            found = []
        known = {x.get("page_url") for x in places.get(poi["poi_id"], [])}
        new = [x for x in found if x["page_url"] not in known]
        if new:
            team = [x for x in places.get(poi["poi_id"], []) if x.get("source") == "team"]
            rest = [x for x in places.get(poi["poi_id"], []) if x.get("source") != "team"]
            places[poi["poi_id"]] = team + new + rest
            added += len(new)
        time.sleep(1.2)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=0))
    print(f"name search: {added} photos added for {len(pois)} named places")


def main():
    pois = [p for p in json.loads((ROOT / "data/poi.json").read_text()) if p["category"] in RADIUS]
    old = json.loads(OUT.read_text()) if OUT.exists() else {"places": {}}
    places = {pid: [x for x in items if x.get("source") == "team"] for pid, items in old.get("places", {}).items()}
    for n, poi in enumerate(pois, 1):
        try:
            found = photos_near(poi)
        except Exception as exc:  # one failed place must not stop the run
            print(f"skip {poi['poi_id']}: {exc}", file=sys.stderr)
            found = []
        if found:
            places[poi["poi_id"]] = places.get(poi["poi_id"], []) + found
        if n % 50 == 0:
            print(f"{n}/{len(pois)} places, {sum(1 for v in places.values() if v)} with photos", flush=True)
        time.sleep(1.2)
    places = {k: v for k, v in places.items() if v}
    OUT.write_text(json.dumps({"version": 1, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "places": places}, ensure_ascii=False, indent=0))
    print(f"done: {len(places)} places with photos -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    by_name() if "--by-name" in sys.argv else main()

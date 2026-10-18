"""Copy the Commons photos from frontend/img/places/index.json onto the website itself.

The backend on Render downloads each photo to show it to Gemini, and Wikimedia does not reliably
serve cloud servers. A small copy next to index.json (same Netlify site) always works and also loads
faster in the browser. Author, license and the Commons page stay in the list, so credits are kept.

    python scripts/host_photos.py        # macOS: shrinks with the built-in `sips`, otherwise keeps size
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACES = ROOT / "frontend/img/places"
INDEX = PLACES / "index.json"
UA = {"User-Agent": "SeruenAstana/1.0 (hackathon walk assistant; https://seruen-astana.netlify.app)"}
PER_PLACE, SIDE, QUALITY = 3, 640, 70


def shrink(raw, target):
    if not shutil.which("sips"):
        target.write_bytes(raw)
        return
    with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
        tmp.write(raw)
        tmp.flush()
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(QUALITY), "-Z", str(SIDE),
                        tmp.name, "--out", str(target)], check=True, capture_output=True)


def main():
    data = json.loads(INDEX.read_text())
    (PLACES / "c").mkdir(exist_ok=True)
    done = failed = 0
    for poi_id, items in data["places"].items():
        kept = [x for x in items if x.get("source") == "team"]
        for item in items:
            if item.get("source") == "team" or len(kept) >= PER_PLACE + sum(x.get("source") == "team" for x in items):
                continue
            url = item["url"]
            if not url.startswith("https://"):  # hosted on an earlier run
                if (PLACES / url).exists():
                    kept.append(item)
                    done += 1
                continue
            name = "c/" + hashlib.sha1(url.split("?")[0].encode()).hexdigest()[:16] + ".jpg"
            target = PLACES / name
            if not target.exists() and url.startswith("https://"):
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                        shrink(r.read(), target)
                    time.sleep(0.3)
                except Exception as exc:  # one missing photo must not stop the run
                    print(f"skip {url[:80]}: {exc}", file=sys.stderr)
                    failed += 1
                    continue
            if target.exists():
                kept.append({**item, "url": name})
                done += 1
        data["places"][poi_id] = kept
    data["places"] = {k: v for k, v in data["places"].items() if v}
    INDEX.write_text(json.dumps(data, ensure_ascii=False, indent=0))
    used = {x["url"] for items in data["places"].values() for x in items}
    for f in (PLACES / "c").glob("*.jpg"):
        if f"c/{f.name}" not in used:
            f.unlink()
    size = sum(f.stat().st_size for f in (PLACES / "c").glob("*.jpg"))
    print(f"{done} photos on the site, {failed} failed, {len(data['places'])} places, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()

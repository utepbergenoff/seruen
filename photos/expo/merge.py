"""Add the EXPO photo set to the app. Run from the seruen repo root:

    python <path-to-this-folder>/merge.py            # check only, changes nothing
    python <path-to-this-folder>/merge.py --apply    # copy photos + update index.json and photo_identity_review.json

Refuses to overwrite: a place that already has photos, or a file that already exists, stops the run.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent
REPO = Path.cwd()
INDEX = REPO / "frontend/img/places/index.json"
REVIEW = REPO / "data/photo_identity_review.json"
PHOTOS = REPO / "frontend/img/places/c"
BASE_URL = "https://seruen-astana.netlify.app/img/places/"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data, indent):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8", newline="\n")


def main(apply):
    if not (INDEX.exists() and REVIEW.exists()):
        sys.exit("Run this from the seruen repo root (frontend/img/places/index.json not found).")
    new_index, new_review = load(PKG / "index_entries.json"), load(PKG / "review_entries.json")
    index, review = load(INDEX), load(REVIEW)
    pois = {p["poi_id"] for p in load(REPO / "data/poi.json")}
    problems = []
    for pid, entries in new_index.items():
        if pid not in pois:
            problems.append(f"{pid}: not in data/poi.json")
        if pid in index["places"] or pid in review["places"]:
            problems.append(f"{pid}: already has photos in the app")
        if set(new_review.get(pid, {})) != {BASE_URL + e["url"] for e in entries}:
            problems.append(f"{pid}: index and review entries do not match")
        for e in entries:
            src, dst = PKG / e["url"], PHOTOS / Path(e["url"]).name
            if not src.exists():
                problems.append(f"{e['url']}: missing in the package")
                continue
            if dst.exists():
                problems.append(f"{dst.name}: already exists in frontend/img/places/c")
            digest = hashlib.sha256(src.read_bytes()).hexdigest()
            if new_review[pid][BASE_URL + e["url"]]["sha256"] != digest:
                problems.append(f"{e['url']}: file was changed after the hash was taken")
    files = sum(len(v) for v in new_index.values())
    if problems:
        sys.exit("STOP, nothing changed:\n- " + "\n- ".join(problems))
    if not apply:
        print(f"OK: {len(new_index)} places, {files} photos can be added. Run again with --apply.")
        return
    for entries in new_index.values():
        for e in entries:
            shutil.copy2(PKG / e["url"], PHOTOS / Path(e["url"]).name)
    index["places"].update(new_index)
    review["places"].update(new_review)
    save(INDEX, index, 1)
    save(REVIEW, review, 2)
    print(f"Added {len(new_index)} places, {files} photos. Next: tests, PR, Netlify deploy, Render redeploy (see README).")


if __name__ == "__main__":
    main("--apply" in sys.argv)

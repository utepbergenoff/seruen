import hashlib
import json
import re
from dataclasses import dataclass

from pydantic import ValidationError

from .geo import haversine, in_astana
from .schemas import POI


def canonical_name(name):
    return re.sub(r"[^\w]", "", name.casefold().replace("ё", "е"))


@dataclass
class Dataset:
    pois: list[POI]
    fingerprint: str
    rejected: int
    duplicates: int

    @property
    def snapshot_date(self):
        dates = [p.last_checked for p in self.pois if p.last_checked]
        return max(dates) if dates else None


def load_pois(path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("POI file must be a JSON array")
    pois, ids, rejected, duplicates = [], set(), 0, 0
    for row in raw:
        try:
            if not isinstance(row, dict):
                raise ValueError("invalid_row")
            row = {
                **row,
                "category": {
                    "cafe": "coffee",
                    "mall": "shopping",
                    "museum": "culture",
                    "bar": "night",
                    "restaurant": "food",
                }.get(row.get("category"), row.get("category")),
            }
            p = POI.model_validate(row)
            if not in_astana(p.lat, p.lon) or not re.search(r"[^\W\d_]", p.name, re.UNICODE):
                raise ValueError("invalid_place")
            p = p.model_copy(update={"tags": sorted(set(t.casefold().strip() for t in p.tags if t.strip()))})
        except (ValidationError, ValueError, TypeError):
            rejected += 1
            continue
        if p.poi_id in ids or any(
            canonical_name(p.name) == canonical_name(other.name) and haversine(p.lat, p.lon, other.lat, other.lon) < 80
            for other in pois
        ):
            duplicates += 1
            continue
        ids.add(p.poi_id)
        pois.append(p)
    if not pois:
        raise ValueError("POI dataset contains no valid places")
    content = json.dumps([p.model_dump(mode="json") for p in pois], sort_keys=True, ensure_ascii=False)
    return Dataset(pois, hashlib.sha256(content.encode()).hexdigest(), rejected, duplicates)

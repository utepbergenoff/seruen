"""Reviewed team data. Empty production collections mean unknown, never invented facts."""

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from .indoor import indoor_required
from .schemas import Model, POI, VisitConditionView

ComfortKind = Literal["warming", "toilet", "bench", "water", "entrance"]


class Evidence(Model):
    source_url: HttpUrl
    checked_at: date
    verification: Literal["verified", "unverified", "conflicting"]
    method: Literal["field_visit", "official_source", "licensed_source", "team_review"]
    note: str = Field(default="", max_length=800)


class LicensedPlace(Model):
    poi: POI
    evidence: Evidence
    coordinate_evidence: Evidence | None = None
    offline_allowed: bool = False
    license: str = Field(min_length=1, max_length=200)
    attribution: str = Field(min_length=1, max_length=500)


class ComfortRecord(LicensedPlace):
    kind: ComfortKind
    access: Literal["public", "customers_only", "paid", "unknown"] = "unknown"
    floor: str | None = Field(default=None, max_length=80)


class VisitConditionRecord(Model):
    poi_id: str = Field(min_length=1, max_length=120)
    kind: Literal["free", "optional_purchase", "paid", "unknown"]
    evidence: Evidence


class IdentityRecord(Model):
    canonical_id: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(min_length=1, max_length=10)
    evidence: Evidence

    @model_validator(mode="after")
    def distinct(self):
        if self.canonical_id in self.aliases or len(set(self.aliases)) != len(self.aliases):
            raise ValueError("duplicate_identity")
        if any(not x or len(x) > 120 for x in self.aliases):
            raise ValueError("invalid_alias")
        return self


MODELS = {
    "feature_pois.json": LicensedPlace,
    "comfort_points.json": ComfortRecord,
    "visit_conditions.json": VisitConditionRecord,
    "poi_identity_links.json": IdentityRecord,
}


class FeatureData:
    def __init__(self, directory: Path | None, base_pois=()):
        self.pois = {p.poi_id: p for p in base_pois}
        self.owned, self.comfort, self.conditions, self.identities = {}, {}, {}, {}
        self.errors = []
        self.fingerprint = "empty"
        if directory is not None:
            self.load(directory)

    def load(self, directory):
        batches, raw = {}, []
        for name, model in MODELS.items():
            path = Path(directory) / name
            if not path.exists():
                batches[name] = []
                continue
            if path.stat().st_size > 5_000_000:
                raise ValueError(f"feature_data_oversized:{name}")
            content = path.read_text(encoding="utf-8")
            body = json.loads(content)
            if not isinstance(body, dict) or body.get("version") != 1 or set(body) != {"version", "items"}:
                raise ValueError(f"feature_data_format:{name}")
            if not isinstance(body["items"], list) or len(body["items"]) > 5000:
                raise ValueError(f"feature_data_size:{name}")
            batches[name] = [model.model_validate(x) for x in body["items"]]
            raw.append(content)
        self.fingerprint = hashlib.sha256("".join(raw).encode()).hexdigest()
        for name in ("feature_pois.json", "comfort_points.json"):
            for record in batches[name]:
                pid = record.poi.poi_id
                if pid in self.pois or pid in self.owned or pid.startswith("2gis_"):
                    raise ValueError("feature_place_id_conflict")
                from .geo import in_astana
                if not in_astana(record.poi.lat, record.poi.lon):
                    raise ValueError("feature_place_outside_city")
                self.pois[pid] = record.poi
                self.owned[pid] = record
                if name == "comfort_points.json":
                    self.comfort[pid] = record
        occupied = set()
        for record in batches["poi_identity_links.json"]:
            if record.evidence.verification != "verified" or record.canonical_id not in self.pois:
                raise ValueError("identity_not_verified_or_unknown_canonical")
            group = [record.canonical_id, *record.aliases]
            if occupied.intersection(group):
                raise ValueError("identity_overlap")
            occupied.update(group)
            for pid in group:
                self.identities[pid] = record.canonical_id
        for record in batches["visit_conditions.json"]:
            key = self.canonical(record.poi_id)
            if key not in self.pois and not key.startswith("2gis_"):
                raise ValueError("conditions_unknown_place")
            if key in self.conditions:
                raise ValueError("conditions_duplicate_place")
            self.conditions[key] = record

    def canonical(self, poi_id):
        return self.identities.get(poi_id, poi_id)

    def twogis_id(self, poi_id):
        """Use only an explicit branch ID or one unambiguous reviewed identity."""
        canonical = self.canonical(poi_id)
        poi = self.pois.get(poi_id) or self.pois.get(canonical)
        ids = {pid.removeprefix("2gis_") for pid, owner in self.identities.items()
               if owner == canonical and pid.startswith("2gis_") and pid[5:].isdigit()}
        if poi and poi.twogis_place_id:
            ids.add(poi.twogis_place_id)
        return next(iter(ids)) if len(ids) == 1 else None

    def can_export(self, poi_id, today):
        record = self.owned.get(self.canonical(poi_id))
        return bool(record and record.offline_allowed and self.verified(record.evidence, today))

    @staticmethod
    def verified(evidence, today, max_age=90):
        return evidence.verification == "verified" and 0 <= (today - evidence.checked_at).days <= max_age

    def condition(self, poi_id, today, poi=None):
        result = self._condition(poi_id, today)
        if poi and poi.twogis_place_id and "2gis" in poi.sources:
            result.provider_attributes = poi.provider_attributes
            result.provider_url = poi.description_url or f"https://2gis.kz/astana/firm/{poi.twogis_place_id}"
        return result

    def _condition(self, poi_id, today):
        record = self.conditions.get(self.canonical(poi_id))
        if not record:
            comfort = self.comfort.get(self.canonical(poi_id))
            if comfort and comfort.access == "public" and self.verified(comfort.evidence, today, 30):
                return VisitConditionView(kind="free", note=comfort.evidence.note,
                    source_url=str(comfort.evidence.source_url), checked_at=comfort.evidence.checked_at,
                    verification="verified")
            return VisitConditionView()
        valid = self.verified(record.evidence, today, 30)
        status = record.evidence.verification if record.evidence.verification != "verified" else (
            "verified" if valid else "stale")
        return VisitConditionView(kind=record.kind if valid else "unknown", note=record.evidence.note,
                                  source_url=str(record.evidence.source_url), checked_at=record.evidence.checked_at,
                                  verification=status)

    def constraint(self, poi, preferences, walk, today, comfort=False):
        pid = self.canonical(poi.poi_id)
        owned = self.owned.get(pid)
        if owned and not self.verified(owned.evidence, today):
            return "team_place_unverified"
        if pid in {self.canonical(x) for x in preferences.exclude_poi_ids}:
            return "excluded_place"
        if preferences.exclude_visited and pid in {self.canonical(x) for x in preferences.visited_poi_ids}:
            return "already_visited"
        if not comfort and preferences.preferred_categories and poi.category not in preferences.preferred_categories:
            return "preferred_category_mismatch"
        if preferences.max_walk_min is not None and walk > preferences.max_walk_min:
            return "walking_limit"
        if preferences.indoor_only and not poi.indoor:
            return "indoor_required"
        mode, kind = preferences.expense_mode, self.condition(poi.poi_id, today).kind
        if mode == "free_only" and kind != "free":
            return "free_access_unconfirmed"
        if mode == "no_required_purchase" and kind not in ("free", "optional_purchase"):
            return "no_purchase_unconfirmed"
        return None


def apply_feedback(request):
    """Apply text constraints and feedback to a copy, shared by discovery, recommendations and plans."""
    request = request.model_copy(deep=True)
    feedback, prefs = request.feedback, request.preferences
    prefs.indoor_only = indoor_required(request)
    if not feedback:
        return request
    if feedback.reason == "too_far":
        prefs.max_walk_min = min(prefs.max_walk_min or 120, feedback.max_walk_min or 5)
    elif feedback.reason == "already_visited":
        prefs.visited_poi_ids = list(dict.fromkeys([*prefs.visited_poi_ids, feedback.poi_id]))
        prefs.exclude_visited = True
    elif feedback.reason == "different_place":
        prefs.exclude_poi_ids = list(dict.fromkeys([*prefs.exclude_poi_ids, feedback.poi_id]))
    elif feedback.reason == "wrong_type":
        request.context.exclude_categories = list(dict.fromkeys([*request.context.exclude_categories, feedback.category]))
    elif feedback.reason == "no_expense":
        prefs.expense_mode = "no_required_purchase"
    return request


def relaxation_options(preferences):
    result = []
    if preferences.max_walk_min:
        result.append("increase_walk_limit")
    if preferences.max_distance_m:
        result.append("increase_distance_limit")
    if preferences.indoor_only:
        result.append("allow_outdoor")
    if preferences.expense_mode != "any":
        result.append("allow_unknown_expenses")
    if preferences.exclude_visited:
        result.append("include_visited")
    if preferences.exclude_poi_ids:
        result.append("restore_excluded_places")
    if preferences.preferred_categories:
        result.append("change_preferred_categories")
    return result


def feedback_note(reason, lang):
    rows = {
        "too_far": ("Сократили допустимое время ходьбы.", "Reduced the walking-time limit.", "Жаяу жүру уақытының шегі қысқартылды."),
        "already_visited": ("Исключили отмеченные посещённые места.", "Excluded places you marked as visited.", "Барған деп белгіленген орындар алынып тасталды."),
        "different_place": ("Исключили выбранное место и ищем замену.", "Excluded that place and looked for alternatives.", "Таңдалған орын алынып тасталды, балама ізделуде."),
        "wrong_type": ("Исключили указанную категорию.", "Excluded the selected category.", "Таңдалған санат алынып тасталды."),
        "no_expense": ("Оставили места без подтверждённых обязательных расходов; неизвестные условия исключены.",
                       "Kept places confirmed to require no purchase; unknown conditions are excluded.",
                       "Міндетті шығынсыз орындар ғана қалды; шарты белгісіз орындар алынып тасталды."),
    }
    return rows[reason][{"ru": 0, "en": 1, "kk": 2}[lang]]

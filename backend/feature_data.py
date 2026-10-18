"""Reviewed team data. Empty production collections mean unknown, never invented facts."""

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from .schemas import AtmosphereMatch, Model, POI, VisitConditionView

VisualFeature = Literal[
    "natural_light", "bright", "dim", "greenery", "open_space", "small_space",
    "visible_seating", "modern", "traditional", "unusual_architecture", "outdoor", "indoor",
]
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


class AtmospherePhoto(Model):
    photo_id: str = Field(min_length=1, max_length=120)
    url: HttpUrl
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    license: str = Field(min_length=1, max_length=200)
    attribution: str = Field(min_length=1, max_length=500)
    offline_allowed: bool = False


class AtmosphereRecord(Model):
    example_id: str = Field(min_length=1, max_length=120)
    poi_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    features: list[VisualFeature] = Field(min_length=1, max_length=12)
    photos: list[AtmospherePhoto] = Field(min_length=1, max_length=4)
    evidence: Evidence
    analysis_source: Literal["manual", "gemini"]
    analysis_version: str = Field(min_length=1, max_length=80)


MODELS = {
    "feature_pois.json": LicensedPlace,
    "comfort_points.json": ComfortRecord,
    "visit_conditions.json": VisitConditionRecord,
    "poi_identity_links.json": IdentityRecord,
    "atmosphere_catalog.json": AtmosphereRecord,
}


class FeatureData:
    def __init__(self, directory: Path | None, base_pois=()):
        self.pois = {p.poi_id: p for p in base_pois}
        self.owned, self.comfort, self.conditions, self.identities, self.atmosphere = {}, {}, {}, {}, {}
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
        photo_ids, photo_owners = set(), {}
        for record in batches["atmosphere_catalog.json"]:
            if record.example_id in self.atmosphere or self.canonical(record.poi_id) not in self.pois:
                raise ValueError("atmosphere_duplicate_or_unknown_place")
            ids = [p.photo_id for p in record.photos]
            if len(set(ids)) != len(ids) or photo_ids.intersection(ids):
                raise ValueError("atmosphere_duplicate_photo")
            photo_ids.update(ids)
            for photo in record.photos:
                owner = self.canonical(record.poi_id)
                if photo.content_sha256 in photo_owners and photo_owners[photo.content_sha256] != owner:
                    raise ValueError("atmosphere_photo_multiple_places")
                photo_owners[photo.content_sha256] = owner
            self.atmosphere[record.example_id] = record

    def canonical(self, poi_id):
        return self.identities.get(poi_id, poi_id)

    @staticmethod
    def verified(evidence, today, max_age=90):
        return evidence.verification == "verified" and 0 <= (today - evidence.checked_at).days <= max_age

    def condition(self, poi_id, today):
        record = self.conditions.get(self.canonical(poi_id))
        if not record:
            return VisitConditionView()
        valid = self.verified(record.evidence, today, 30)
        status = record.evidence.verification if record.evidence.verification != "verified" else (
            "verified" if valid else "stale")
        return VisitConditionView(kind=record.kind if valid else "unknown", note=record.evidence.note,
                                  source_url=str(record.evidence.source_url), checked_at=record.evidence.checked_at,
                                  verification=status)

    def examples(self, today):
        return [r for r in self.atmosphere.values() if self.verified(r.evidence, today)]

    def match(self, poi_id, example_id, today):
        example = self.atmosphere.get(example_id)
        if not example or not self.verified(example.evidence, today):
            return AtmosphereMatch()
        best = AtmosphereMatch()
        for row in self.examples(today):
            if self.canonical(row.poi_id) != self.canonical(poi_id):
                continue
            overlap = sorted(set(example.features) & set(row.features))
            if len(overlap) > len(best.matched_features):
                best = AtmosphereMatch(matched_features=overlap, source=row.analysis_source,
                                       checked_at=row.evidence.checked_at, photo_ids=[p.photo_id for p in row.photos])
        return best

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
        if not comfort and preferences.atmosphere_example_id and not self.match(poi.poi_id, preferences.atmosphere_example_id,
                                                                today).matched_features:
            return "atmosphere_unconfirmed"
        return None


def apply_feedback(request):
    """Stateless: undo means resend the previous preferences without feedback."""
    request = request.model_copy(deep=True)
    feedback, prefs = request.feedback, request.preferences
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
    if preferences.indoor_only:
        result.append("allow_outdoor")
    if preferences.expense_mode != "any":
        result.append("allow_unknown_expenses")
    if preferences.atmosphere_example_id:
        result.append("remove_atmosphere_filter")
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

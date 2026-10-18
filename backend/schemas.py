from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

Category = Literal[
    "coffee",
    "food",
    "park",
    "kids",
    "culture",
    "viewpoint",
    "shopping",
    "sport",
    "night",
    "unusual",
    "library",
    "cowork",
]
Lang = Literal["ru", "kk", "en"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Correlated(Model):
    request_id: str | None = Field(default=None, min_length=1, max_length=40)


class Coords(Model):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Location(Coords):
    precision_m: int = Field(default=100, ge=100, le=10000)
    source: Literal["gps", "map", "preset"] = "preset"

    @field_validator("lat", "lon")
    @classmethod
    def round_location(cls, value):
        return round(value, 3)


class Weather(Model):
    temp_c: float = Field(ge=-70, le=60)
    wind_ms: float = Field(ge=0, le=100)
    precip_mm: float = Field(default=0, ge=0, le=1000)


class Context(Model):
    time_budget_min: int | None = Field(default=None, ge=5, le=480)
    companions: Literal["alone", "child", "group"] = "alone"
    mode: Literal["walk"] = "walk"
    now: AwareDatetime | None = None
    lang: Literal["ru", "kk", "en", "auto"] = "auto"
    accessibility: bool = False
    exclude_categories: list[Category] = Field(default_factory=list, max_length=12)
    weather: Weather | None = None
    simulate: bool = False

    @field_validator("exclude_categories", mode="before")
    @classmethod
    def aliases(cls, value):
        return ["shopping" if x == "mall" else x for x in value] if isinstance(value, list) else value


class Preferences(Model):
    exclude_poi_ids: list[str] = Field(default_factory=list, max_length=200)
    visited_poi_ids: list[str] = Field(default_factory=list, max_length=200)
    exclude_visited: bool = False
    preferred_categories: list[Category] = Field(default_factory=list, max_length=12)
    max_walk_min: int | None = Field(default=None, ge=1, le=120)
    max_distance_m: int | None = Field(default=None, ge=50, le=10000)
    indoor_only: bool = False
    expense_mode: Literal["any", "free_only", "no_required_purchase"] = "any"
    atmosphere_example_id: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("exclude_poi_ids", "visited_poi_ids")
    @classmethod
    def bounded_ids(cls, value):
        if any(not x or len(x) > 120 for x in value):
            raise ValueError("invalid_poi_id")
        return list(dict.fromkeys(value))


class Feedback(Model):
    reason: Literal["too_far", "already_visited", "different_place", "wrong_type", "no_expense"]
    poi_id: str | None = Field(default=None, min_length=1, max_length=120)
    category: Category | None = None
    max_walk_min: int | None = Field(default=None, ge=1, le=120)

    @model_validator(mode="after")
    def required_context(self):
        if self.reason in ("already_visited", "different_place") and not self.poi_id:
            raise ValueError("poi_id_required")
        if self.reason == "wrong_type" and not self.category:
            raise ValueError("category_required")
        return self


class VisitConditionView(Model):
    kind: Literal["free", "optional_purchase", "paid", "unknown"] = "unknown"
    note: str = ""
    source_url: str | None = None
    checked_at: date | None = None
    verification: Literal["verified", "unverified", "conflicting", "stale", "unknown"] = "unknown"


class AtmosphereMatch(Model):
    matched_features: list[str] = Field(default_factory=list)
    source: Literal["manual", "gemini", "none"] = "none"
    checked_at: date | None = None
    photo_ids: list[str] = Field(default_factory=list)


class RecommendRequest(Correlated):
    location: Location
    end: Location | None = None
    query: str = Field(default="", max_length=1000)
    context: Context = Field(default_factory=Context)
    source: Literal["auto", "local", "2gis"] = "auto"
    cursor: str | None = Field(default=None, max_length=100)
    preferences: Preferences = Field(default_factory=Preferences)
    feedback: Feedback | None = None

    @model_validator(mode="after")
    def feedback_capacity(self):
        if self.feedback and self.feedback.reason in ("different_place", "already_visited"):
            ids = (self.preferences.exclude_poi_ids if self.feedback.reason == "different_place"
                   else self.preferences.visited_poi_ids)
            if self.feedback.poi_id not in ids and len(ids) >= 200:
                raise ValueError("too_many_exclusions")
        return self


class POI(Model):
    poi_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=2, max_length=200)
    name_kk: str | None = None
    name_en: str | None = None
    name_generic: bool = False
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    category: Category
    tags: list[str] = Field(default_factory=list)
    tags_inferred: list[str] = Field(default_factory=list)
    google_place_id: str | None = Field(default=None, max_length=255)
    twogis_place_id: str | None = Field(default=None, pattern=r"^[0-9]{1,32}$")
    description_url: str | None = None
    description: str = Field(default="", max_length=2000)
    description_source: Literal["wikipedia", "source", "generated"] = "source"
    opening_hours_raw: str | None = None
    hours_source: Literal["2gis", "osm", "none"] = "none"
    hours_conflict: bool = False
    phone: str | None = None
    website: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    rating_count: int | None = Field(default=None, ge=0)
    popularity: float = Field(default=0, ge=0, le=1)
    wheelchair: Literal["yes", "limited", "no", "unknown"] = "unknown"
    kid_friendly: bool = False
    adult_only: bool = False
    indoor: bool = False
    sources: list[str] = Field(default_factory=list)
    last_checked: date | None = None
    chain: str | None = None
    temporary: bool = False
    event_start: AwareDatetime | None = None
    event_end: AwareDatetime | None = None
    event_source: str | None = None


class Intent(Model):
    categories: list[Category] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    time_budget_min: int = Field(default=60, ge=5, le=480)
    companions: Literal["alone", "child", "group"] = "alone"
    when: Literal["now", "evening", "tomorrow", "night"] = "now"
    lang: Lang = "ru"
    exclude_categories: list[Category] = Field(default_factory=list)
    before_flight: bool = False
    relevant: bool = True
    unsafe: bool = False


class OpenStatus(Model):
    state: Literal["open", "likely_open", "unknown", "closed"]
    confidence: Literal["high", "medium", "low"]
    hours: str | None
    source: Literal["2gis", "osm", "none"]
    checked_at: date | None


class Budget(Model):
    walk_there_min: int = Field(ge=0)
    stay_min: int = Field(ge=0)
    walk_back_min: int = Field(ge=0)
    walk_to_end_min: int | None = Field(default=None, ge=0)
    reserve_min: int = Field(default=0, ge=0)
    total_min: int = Field(ge=0)


class Recommendation(Model):
    poi_id: str
    canonical_id: str | None = None
    name: str
    category: Category
    coords: Coords
    distance_m: int = Field(ge=0)
    walk_min: int = Field(ge=0)
    why: str = Field(min_length=1)
    why_source: Literal["ai", "template"]
    selection_source: Literal["ai", "rules"] = "rules"
    time_to_spend_min: int = Field(ge=1)
    what_to_do: str = Field(min_length=1)
    what_to_do_source: Literal["ai", "template"]
    open_status: OpenStatus
    facts_source: Literal["poi_db", "2gis"] = "poi_db"
    address: str | None = None
    description_source: Literal["wikipedia", "source", "generated"]
    description: str = ""
    description_url: str | None = None
    sources: list[str] = Field(default_factory=list)
    last_checked: date | None = None
    accessibility: Literal["yes", "limited", "no", "unknown"]
    links: dict[str, str]
    rating: float | None
    rating_count: int | None
    budget_breakdown: Budget
    visit_condition: VisitConditionView = Field(default_factory=VisitConditionView)
    atmosphere_match: AtmosphereMatch = Field(default_factory=AtmosphereMatch)
    arrival_estimate: datetime | None = None
    offline_allowed: bool = False

    @field_validator("why", "what_to_do")
    @classmethod
    def word_limit(cls, value, info):
        if len(value.split()) > (25 if info.field_name == "why" else 35):
            raise ValueError("word_limit")
        return value


class Considered(Model):
    location_rounded_to_m: int = 100
    radius_m: int
    radius_expanded: bool
    time_budget_min: int
    effective_budget_min: int = Field(default=0, ge=0)
    reserve_min: int = Field(default=0, ge=0)
    walk_speed_m_per_min: int = 75
    street_factor: float = 1.3
    companions: Literal["alone", "child", "group"] = "alone"
    time_simulated: bool = False
    lang: Lang = "ru"
    filters: list[str]
    time: str
    candidates_found: int
    weather: Weather | None = None
    retrieval_mode: str = "bm25"
    intent_source: Literal["rules", "ai"] = "rules"
    target_time: datetime


class Candidate(Model):
    poi_id: str
    name: str
    category: Category
    distance_m: int
    walk_min: int
    score: float
    reasons: list[str]
    excluded_because: str | None = None


class CatalogPlace(Model):
    poi_id: str
    canonical_id: str | None = None
    name: str
    category: Category
    coords: Coords
    distance_m: int
    walk_min: int
    address: str | None = None
    rating: float | None = None
    rating_count: int | None = None
    open_status: OpenStatus
    eligible: bool
    excluded_because: str | None = None
    links: dict[str, str]


class RouteSuggestion(Model):
    kind: Literal["more_time", "fewer_stops"]
    min: int | None = Field(default=None, ge=5, le=480)


class RouteImpossible(Model):
    reason: Literal["budget", "distance"]
    need_min: int = Field(ge=0)
    suggestions: list[RouteSuggestion] = Field(default_factory=list, max_length=2)


class RecommendResponse(Correlated):
    candidates: list[Candidate] = Field(default_factory=list, max_length=30)
    excluded: list[Candidate] = Field(default_factory=list, max_length=20)
    excluded_count: int = Field(default=0, ge=0)
    mode: Literal["ai", "no_ai", "cached"]
    recommendations: list[Recommendation] = Field(max_length=3)
    budget_breakdown: Budget | None
    considered: Considered
    notes: list[str]
    safety: list[str]
    route: None = None
    disclaimer: str
    data_kind: Literal["sample", "real"]
    mock: bool = False
    source: Literal["local", "2gis"] = "local"
    next_cursor: str | None = None
    source_error: str | None = None
    nearby_places: list[CatalogPlace] = Field(default_factory=list, max_length=30)
    catalog_total: int | None = Field(default=None, ge=0)
    applied_preferences: Preferences = Field(default_factory=Preferences)
    change_codes: list[str] = Field(default_factory=list)
    relaxation_options: list[str] = Field(default_factory=list)
    route_impossible: RouteImpossible | None = None


class PlacesStatus(Model):
    configured: bool
    details_enabled: bool
    ids_probe: str


class Health(Model):
    status: Literal["ok"] = "ok"
    mode_available: list[str]
    data_snapshot_date: date | None
    poi_count: int
    data_kind: Literal["sample", "real"]
    retrieval_mode: str
    mock: bool
    google_places: PlacesStatus | None = None
    twogis: "TwoGisStatus | None" = None
    feature_contract_version: int = 2
    features: dict[str, int] = Field(default_factory=lambda: {
        "replan": 1, "end_point": 1, "constraints": 1, "comfort": 1,
        "cost": 1, "atmosphere": 1, "plan_export": 1, "nearby_break": 1,
    })


class TwoGisStatus(Model):
    configured: bool
    enabled: bool
    last_status: str
    photos_supported: bool = False
    search_enabled: bool = False


class Draft(Model):
    poi_id: str
    why: str = Field(min_length=1, max_length=700)
    time_to_spend_min: int = Field(ge=1, le=480)
    what_to_do: str = Field(min_length=1, max_length=1000)


class Generated(Model):
    recommendations: list[Draft] = Field(min_length=1, max_length=3)
    note_to_user: str = Field(default="", max_length=500)

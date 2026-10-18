from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

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


class RecommendRequest(Model):
    location: Location
    query: str = Field(default="", max_length=1000)
    context: Context = Field(default_factory=Context)


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
    reserve_min: int = Field(default=0, ge=0)
    total_min: int = Field(ge=0)


class Recommendation(Model):
    poi_id: str
    name: str
    category: Category
    coords: Coords
    distance_m: int = Field(ge=0)
    walk_min: int = Field(ge=0)
    why: str = Field(min_length=1)
    why_source: Literal["ai", "template"]
    time_to_spend_min: int = Field(ge=1)
    what_to_do: str = Field(min_length=1)
    what_to_do_source: Literal["ai", "template"]
    open_status: OpenStatus
    facts_source: Literal["poi_db"] = "poi_db"
    description_source: Literal["wikipedia", "source", "generated"]
    description_url: str | None = None
    accessibility: Literal["yes", "limited", "no", "unknown"]
    links: dict[str, str]
    rating: float | None
    rating_count: int | None
    budget_breakdown: Budget

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
    filters: list[str]
    time: str
    candidates_found: int
    weather: Weather | None = None
    retrieval_mode: str = "bm25"
    intent_source: Literal["rules", "ai"] = "rules"
    target_time: datetime


class RecommendResponse(Model):
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


class Candidate(Model):
    poi_id: str
    name: str
    category: Category
    distance_m: int
    walk_min: int
    score: float
    reasons: list[str]
    excluded_because: str | None = None


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


class Draft(Model):
    poi_id: str
    why: str = Field(min_length=1, max_length=700)
    time_to_spend_min: int = Field(ge=1, le=480)
    what_to_do: str = Field(min_length=1, max_length=1000)


class Generated(Model):
    recommendations: list[Draft] = Field(min_length=1, max_length=3)
    note_to_user: str = Field(default="", max_length=500)

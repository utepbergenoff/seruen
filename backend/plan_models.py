"""Version 1 public walking-plan contract. Client state contains IDs, never trusted POI facts."""

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from .schemas import (AtmosphereMatch, Category, Coords, Location, Model, OpenStatus, Preferences,
                      RecommendRequest, VisitConditionView)
from .feature_data import ComfortKind

Id = Annotated[str, Field(min_length=1, max_length=120)]


class PlanState(Model):
    schema_version: Literal[1] = 1
    created_at: AwareDatetime
    origin: Location
    finish_mode: Literal["return", "destination"]
    finish: Location
    remaining_ids: list[Id] = Field(default_factory=list, max_length=5)
    completed_ids: list[Id] = Field(default_factory=list, max_length=200)
    skipped_ids: list[Id] = Field(default_factory=list, max_length=200)
    preferences: Preferences = Field(default_factory=Preferences)
    exclude_categories: list[Category] = Field(default_factory=list, max_length=12)
    companions: Literal["alone", "child", "group"] = "alone"
    accessibility: bool = False
    reserve_min: int = Field(default=5, ge=0, le=120)


class PlanRequest(Model):
    request: RecommendRequest
    finish_mode: Literal["return", "destination"] = "return"
    destination: Location | None = None
    origin: Location | None = None
    stop_ids: list[Id] = Field(default_factory=list, max_length=5)
    completed_ids: list[Id] = Field(default_factory=list, max_length=200)
    skipped_ids: list[Id] = Field(default_factory=list, max_length=200)
    reserve_min: int = Field(default=5, ge=0, le=120)
    max_stops: int = Field(default=3, ge=1, le=5)

    @model_validator(mode="after")
    def coherent(self):
        if self.finish_mode == "destination" and self.destination is None:
            raise ValueError("destination_required")
        if self.request.cursor:
            raise ValueError("plan_does_not_accept_cursor")
        ids = self.stop_ids + self.completed_ids + self.skipped_ids
        if any(not p or len(p) > 120 for p in ids):
            raise ValueError("invalid_poi_id")
        if len(set(self.stop_ids)) != len(self.stop_ids):
            raise ValueError("duplicate_stop")
        return self


class ReplanRequest(Model):
    request: RecommendRequest
    previous: PlanState
    reason: Literal["less_time", "cold", "tired", "closed", "busy", "skip", "add_stop", "refresh"]
    remaining_time_min: int = Field(ge=5, le=480)
    completed_ids: list[Id] = Field(default_factory=list, max_length=5)
    poi_id: str | None = Field(default=None, min_length=1, max_length=120)
    reserve_min: int = Field(default=5, ge=0, le=120)

    @model_validator(mode="after")
    def reason_context(self):
        if self.reason in ("closed", "busy", "skip", "add_stop") and self.poi_id is None:
            raise ValueError("poi_id_required")
        return self


class PlanLeg(Model):
    from_id: str
    to_id: str
    distance_m: int = Field(ge=0)
    walk_min: int = Field(ge=0)
    source: Literal["osrm_foot", "distance_estimate"]


class PlanStop(Model):
    poi_id: str
    canonical_id: str
    name: str
    category: str
    coords: Coords
    arrival_at: AwareDatetime
    departure_at: AwareDatetime
    stay_min: int = Field(ge=1)
    open_status: OpenStatus
    visit_condition: VisitConditionView
    atmosphere_match: AtmosphereMatch
    sources: list[str]


class PlanBudget(Model):
    available_min: int
    walking_min: int
    visiting_min: int
    reserve_min: int
    total_min: int
    spare_min: int


class PlanExclusion(Model):
    poi_id: str
    reason: str


class PlanResponse(Model):
    schema_version: Literal[1] = 1
    status: Literal["ok", "partial", "impossible", "no_matches", "unavailable", "refused"]
    fits: bool
    stops: list[PlanStop]
    legs: list[PlanLeg]
    budget: PlanBudget
    state: PlanState
    departure_at: AwareDatetime
    estimated_arrival_at: AwareDatetime
    routing_source: Literal["osrm_foot", "distance_estimate"]
    routing_error: str | None = None
    geometry: list[list[float]] = Field(default_factory=list, max_length=5000)
    exclusions: list[PlanExclusion] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    applied_preferences: Preferences
    change_codes: list[str] = Field(default_factory=list)
    relaxation_options: list[str] = Field(default_factory=list)
    data_kind: Literal["sample", "real"]
    source: Literal["local", "2gis"]
    source_error: str | None = None


class ComfortRequest(Model):
    location: Location
    route_points: list[Location] = Field(default_factory=list, max_length=20)
    kinds: list[ComfortKind] = Field(default_factory=list, max_length=5)
    radius_m: int = Field(default=500, ge=50, le=2000)
    public_only: bool = False
    verified_only: bool = True


class ComfortView(Model):
    poi_id: str
    name: str
    coords: Coords
    kind: ComfortKind
    access: Literal["public", "customers_only", "paid", "unknown"]
    distance_to_route_m: int
    floor: str | None
    note: str
    source_url: str
    checked_at: date
    verified: bool


class OfflineRequest(Model):
    schema_version: Literal[1] = 1
    plan: PlanRequest


class OfflineStop(Model):
    poi_id: str
    name: str
    coords: Coords
    category: str
    stay_min: int
    sources: list[str]
    checked_at: date
    license: str
    attribution: str


class OfflinePlan(Model):
    schema_version: Literal[1] = 1
    saved_at: AwareDatetime
    status: Literal["saved", "not_exportable", "revalidation_failed"]
    stops: list[OfflineStop] = Field(max_length=5)
    omitted_ids: list[Id] = Field(max_length=5)
    contains_full_route: bool
    budget: PlanBudget | None = None
    origin: Location | None = None
    finish: Location | None = None
    warning_codes: list[str] = Field(max_length=20)
    notes: list[str] = Field(max_length=20)


class OfflineRefreshRequest(Model):
    saved: OfflinePlan
    request: RecommendRequest
    reserve_min: int = Field(default=5, ge=0, le=120)


class IdentityRequest(Model):
    poi_ids: list[str] = Field(max_length=200)

    @model_validator(mode="after")
    def bounded(self):
        if any(not p or len(p) > 120 for p in self.poi_ids):
            raise ValueError("invalid_poi_id")
        return self

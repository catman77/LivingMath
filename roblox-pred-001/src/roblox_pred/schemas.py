"""Versioned records: observation time is not a game's creation/release time."""
from datetime import UTC, datetime, time, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return value.astimezone(UTC)


def target_window(as_of: datetime, first_day: int = 61, last_day: int = 90) -> tuple[datetime, datetime]:
    """UTC calendar days61..90, inclusive days, exclusive end; requires91-day embargo."""
    start = datetime.combine(utc(as_of).date(), time(), tzinfo=UTC)
    return start + timedelta(days=first_day), start + timedelta(days=last_day + 1)


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class FeatureValue(Record):
    value: float | str | None
    known_at: datetime
    source_observed_at: datetime
    source_id: str = Field(min_length=1)
    source_version_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    capture_kind: Literal['LIVE_RESPONSE', 'HISTORICAL_CAPTURE', 'SYNTHETIC'] = 'LIVE_RESPONSE'
    capture_evidence: str | None = None

    _times = field_validator('known_at', 'source_observed_at')(utc)


class Sample(Record):
    sample_id: str = Field(min_length=1)
    universe_id: StrictInt = Field(gt=0)
    creator_key: str | None
    creator_known_at: datetime
    clone_group_id: str | None = None
    clone_known_at: datetime | None = None
    as_of: datetime
    scenario: Literal['P0', 'P7', 'P30', 'Pfirst']
    release_date: datetime | None
    release_precision: Literal['EXACT', 'DAY', 'UNKNOWN']
    release_evidence: str | None = None
    cohort_frame: str = Field(min_length=1)
    source_id: str
    source_license: str = Field(min_length=1)
    features: dict[str, FeatureValue]
    outcome_metric: str
    outcome_window_start: datetime
    horizon_end: datetime
    outcome: float | None = Field(default=None, ge=0)
    outcome_days: int = Field(default=0, ge=0, le=30)
    outcome_available_at: datetime | None = None
    eligibility_flags: list[str] = Field(default_factory=list)
    censoring_flags: list[str] = Field(default_factory=list)
    synthetic: bool = False

    @field_validator('creator_known_at', 'clone_known_at', 'as_of', 'release_date',
                     'outcome_window_start', 'horizon_end', 'outcome_available_at')
    @classmethod
    def times(cls, value: datetime | None) -> datetime | None:
        return utc(value) if value is not None else value


class Game(Record):
    record_id: str
    universe_id: StrictInt = Field(gt=0)
    creator_id: StrictInt | None = Field(default=None, gt=0)
    creator_type: Literal['User', 'Group', 'UNKNOWN'] = 'UNKNOWN'
    creation_date: datetime | None = None
    release_date: datetime | None = None
    release_precision: Literal['EXACT', 'DAY', 'UNKNOWN'] = 'UNKNOWN'
    release_evidence: str | None = None
    genre: str | None = None
    known_at: datetime
    source_id: str
    source_license: str
    source_provenance: dict[str, Any]

    @field_validator('creation_date', 'release_date', 'known_at')
    @classmethod
    def times(cls, value: datetime | None) -> datetime | None:
        return utc(value) if value is not None else value


class Snapshot(Record):
    record_id: str
    universe_id: StrictInt = Field(gt=0)
    observed_at: datetime
    ingested_at: datetime
    source_id: str
    title: str | None = None
    description: str | None = None
    thumbnail_ref: str | None = None
    visits_total: StrictInt | None = Field(default=None, ge=0)
    current_players: StrictInt | None = Field(default=None, ge=0)
    favorites: StrictInt | None = Field(default=None, ge=0)
    likes: StrictInt | None = Field(default=None, ge=0)
    dislikes: StrictInt | None = Field(default=None, ge=0)
    status: Literal['OBSERVED', 'UNAVAILABLE_UNKNOWN', 'PRIVATE_CONFIRMED', 'DELETED_CONFIRMED']
    source_license: str
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_provenance: dict[str, Any]

    _times = field_validator('observed_at', 'ingested_at')(utc)


class ConceptArtifact(Record):
    record_id: str
    universe_id: StrictInt = Field(gt=0)
    known_at: datetime
    source_observed_at: datetime
    source_id: str
    source_license: str
    source_sha256: str
    text: str
    artifact_kind: str

    _times = field_validator('known_at', 'source_observed_at')(utc)


class Outcome(Record):
    record_id: str
    universe_id: StrictInt
    as_of: datetime
    window_start: datetime
    window_end: datetime
    metric: str
    raw_measure: float | None = None
    success: bool | None = None
    eligibility_flags: list[str] = Field(default_factory=list)
    censoring_flags: list[str] = Field(default_factory=list)
    source_provenance: dict[str, Any]

    _times = field_validator('as_of', 'window_start', 'window_end')(utc)


class SemanticFeatures(Record):
    record_id: str
    sample_id: str
    extractor_version: str
    mcp_version: str | None
    feature_schema: str
    relations: list[dict[str, Any]] | None
    features: dict[str, float] | None
    quality_flags: list[str]
    known_at: datetime
    status: Literal['OK', 'UNSUPPORTED', 'UNAVAILABLE']

    _times = field_validator('known_at')(utc)


class Prediction(Record):
    record_id: str
    experiment_id: str
    model_id: str
    fold: str
    sample_id: str
    score: float = Field(ge=0, le=1)
    calibrated_probability: float | None = Field(default=None, ge=0, le=1)
    as_of: datetime

    _times = field_validator('as_of')(utc)


class Run(Record):
    record_id: str
    experiment_id: str
    git_commit: str | None
    config_sha256: str
    dataset_manifest_sha256: str
    seed: int
    model_versions: dict[str, str]
    timings: dict[str, float]
    status: str

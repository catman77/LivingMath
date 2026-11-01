"""Additive data-only artifact intake. Nothing here is a target graph or executable input."""
from typing import Literal

from davcore.models import StrictModel
from pydantic import Field, model_validator


class ArtifactBudget(StrictModel):
    workers: int = Field(default=64,ge=1,le=128)
    models: int = Field(default=32,ge=1,le=64)
    source_views: int = Field(default=4,ge=1,le=4)
    retries: int = Field(default=2,ge=0,le=3)


class Rights(StrictModel):
    basis: Literal['USER_SESSION','PUBLIC_DOMAIN']
    origin: str = Field(min_length=1,max_length=1000)
    attribution: str = Field(default='',max_length=1000)


class SnapshotRef(StrictModel):
    id: int = Field(ge=1)
    version: int = Field(ge=1)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class ArtifactInput(StrictModel):
    format: Literal['livingmath-artifact/1']
    scope: str = Field(min_length=1,max_length=160,pattern=r'^[\w][\w .:/-]*$')
    source_name: str | None = Field(default=None,min_length=1,max_length=120)
    edition: str | None = Field(default=None,min_length=1,max_length=200)
    language: Literal['en','ru'] | None = None
    rights: Rights | None = None
    raw_text: str | None = Field(default=None,min_length=1,max_length=48000)
    expected_sha256: str | None = Field(default=None,pattern=r'^[a-f0-9]{64}$')
    snapshot: SnapshotRef | None = None
    replaces_snapshot: SnapshotRef | None = None
    profile: Literal['typed008/1'] = 'typed008/1'
    target: Literal['reaction_network'] = 'reaction_network'
    interpretation: Literal['general011', 'observer012', 'observer013', 'meaning014'] | None = Field(default=None, exclude_if=lambda v: v is None)
    budget: ArtifactBudget = Field(default_factory=ArtifactBudget)

    @model_validator(mode='after')
    def data_only(self):
        if (self.raw_text is None)==(self.snapshot is None):
            raise ValueError('EXACTLY_RAW_TEXT_OR_PINNED_SNAPSHOT_REQUIRED')
        if self.snapshot is not None and self.replaces_snapshot is not None:
            raise ValueError('SNAPSHOT_REFERENCE_CANNOT_REPLACE_BYTES')
        if self.raw_text is not None and any(x is None for x in (self.source_name,self.edition,self.language,self.rights)):
            raise ValueError('RAW_SOURCE_METADATA_AND_RIGHTS_REQUIRED')
        if self.raw_text is not None and len(self.raw_text.encode('utf-8'))>48000:
            raise ValueError('ARTIFACT_UTF8_BYTE_BOUND_48000')
        return self

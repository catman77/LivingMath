"""017 staging data contracts. No code, paths, plugins or proof authority."""
from typing import Literal
from pydantic import Field
from native_preview008_contract import DataModel, Project, Checksum, Observer
from typed_cycle011_contract import Text

VERSION = '017.1'
FLAG = 'LIVE_MATH_ENGINE_017'


class Operation017(DataModel):
    ordinal: int = Field(ge=0, le=2)
    name: Text
    definition_sha256: Checksum


class SourceEnvelope017(DataModel):
    schema_version: Literal['livingmath-source017/v1'] = 'livingmath-source017/v1'
    source_id: Text
    project: Project
    scope: Text
    version: int = Field(ge=1)
    origin_sha256: Checksum
    content_sha256: Checksum
    native_definition_sha256: Checksum
    operation_definition_sha256: Checksum
    operations: list[Operation017] = Field(min_length=1, max_length=3)
    observer: Observer
    rights: Text
    provenance: list[Text] = Field(min_length=1, max_length=16)
    unknowns: list[Text] = Field(max_length=32)
    inspection_status: Literal['COMPUTABLE_CHECKED', 'DECLARED_UNINSPECTED']
    law_receipt_sha256: Checksum | None = None
    display_label: Text | None = None


class Query017(DataModel):
    api_version: Literal['engine017/v1'] = 'engine017/v1'
    project: Project
    source_id: Text | None = None
    version: int | None = Field(default=None, ge=1)
    observer: Observer | None = None
    context_level: Literal['C2', 'C4'] = 'C2'
    known_fingerprints: list[Checksum] = Field(default_factory=list, max_length=16)
    latest_feedback: int | None = Field(default=None, ge=1)
    display_label: Text | None = None


def source_identity(envelope):
    from normalizer import digest
    return digest({k: envelope[k] for k in ('project', 'scope', 'origin_sha256', 'content_sha256',
        'native_definition_sha256', 'operation_definition_sha256', 'observer')})

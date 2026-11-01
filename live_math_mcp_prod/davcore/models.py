"""Strict public resource limits shared by finite, SMT and process boundaries."""
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)


class Budget(StrictModel):
    max_states: int = Field(default=1024, ge=1, le=1024)
    max_operations: int = Field(default=200000, ge=1, le=200000)
    max_candidates: int = Field(default=20000, ge=1, le=40000)
    deadline_ms: int = Field(default=5000, ge=1, le=10000)
    max_output_bytes: int = Field(default=1000000, ge=4096, le=2000000)

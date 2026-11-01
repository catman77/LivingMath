"""Configuration and bounded data-governance declarations; not a legal oracle."""
import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, default=str, allow_nan=False).encode()).hexdigest()


def load_config(path: Path) -> tuple[dict, Path]:
    path = path.resolve(strict=True)
    config = yaml.safe_load(path.read_text())
    if ((config['outcome_first_day'], config['outcome_last_day'], config['min_outcome_days']) != (61, 90, 30)
            or config['primary_outcome'] != 'mean_daily_sampled_current_players_d61_90'):
        raise ValueError('OUTCOME_NOT_IMPLEMENTED_REGISTER_NEW_PROTOCOL')
    if config['threshold_quantile_method'] != 'linear' or config['threshold_ties'] != 'greater_or_equal':
        raise ValueError('THRESHOLD_RULE_NOT_IMPLEMENTED')
    if (not 0 <= config['utc_daily_sampling_hour'] <= 23
            or not 0 <= config['sampling_tolerance_minutes'] < 60):
        raise ValueError('INVALID_UTC_SAMPLING_SLOT')
    if config['embargo_days'] < config['outcome_last_day'] + 1:
        raise ValueError('EMBARGO_SHORTER_THAN_CALENDAR_HORIZON')
    if config['audit']['automatic_retries'] != 0:
        raise ValueError('AUDIT_AUTOMATIC_RETRIES_NOT_REGISTERED')
    limits = config['audit']
    if (not 0 < limits['max_requests'] <= 12 or not 0 < limits['max_total_seconds'] <= 60
            or not 0 < limits['timeout_seconds'] <= limits['max_total_seconds']
            or limits['interval_seconds'] < 1 or not 0 < limits['max_response_bytes'] <= 2000000):
        raise ValueError('AUDIT_BOUNDS_REQUIRED')
    return config, path.parent.parent


class SourcePolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: str
    family: str
    documentation_url: str | None
    terms_url: str | None
    rights_status: str
    rights_reason: str
    commercial_allowed: bool
    ml_allowed: bool
    collection_allowed: bool
    historical_snapshots: bool
    sampling_frame_confirmed: bool
    authorization_evidence: str | None
    authorization_sha256: str | None = Field(pattern=r'^[a-f0-9]{64}$')


def registry(root: Path, config: dict) -> dict[str, SourcePolicy]:
    rows = yaml.safe_load((root / config['sources_registry']).read_text())['sources']
    result = {r['source_id']: SourcePolicy.model_validate(r) for r in rows}
    if len(result) != len(rows):
        raise ValueError('DUPLICATE_SOURCE_ID')
    return result


def authorize(policy: SourcePolicy, root: Path, *, collect: bool = False) -> None:
    if (policy.rights_status != 'EXPLICIT_EXCEPTION_OR_LICENSE' or not policy.ml_allowed
            or not policy.commercial_allowed or (collect and not policy.collection_allowed)):
        raise ValueError('SOURCE_RIGHTS_BLOCKED:' + policy.source_id)
    if not policy.authorization_evidence or not policy.authorization_sha256:
        raise ValueError('SOURCE_RIGHTS_EVIDENCE_REQUIRED')
    evidence = (root / policy.authorization_evidence).resolve(strict=True)
    if hashlib.sha256(evidence.read_bytes()).hexdigest() != policy.authorization_sha256:
        raise ValueError('SOURCE_RIGHTS_EVIDENCE_DRIFT')
    # This records an operator-reviewed evidence document, never machine-certified rights.

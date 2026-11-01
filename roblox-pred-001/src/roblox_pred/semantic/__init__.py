"""Adapter boundary, not an invented native solver or heuristic renamed SUTI."""
from roblox_pred.config import digest
from roblox_pred.features import validate_as_of
from roblox_pred.schemas import ConceptArtifact, Sample, SemanticFeatures


def native_contract(sample: Sample, artifacts: list[ConceptArtifact]) -> dict:
    validate_as_of(sample)
    if any(a.universe_id != sample.universe_id or a.known_at > sample.as_of
           or a.source_observed_at > sample.as_of or a.known_at < a.source_observed_at for a in artifacts):
        raise ValueError('SEMANTIC_SOURCE_BINDING_OR_FUTURE_ARTIFACT')
    # Only source views. No outcome, threshold, success label or future history.
    return {'contract': 'roblox_project_structural_features/v1', 'sample_id': sample.sample_id,
        'as_of': sample.as_of.isoformat(), 'source_features': {k: v.model_dump(mode='json')
            for k, v in sample.features.items() if k in {'title', 'description', 'thumbnail_ref'}},
        'artifacts': [a.model_dump(mode='json') for a in artifacts]}


def unavailable(sample: Sample) -> SemanticFeatures:
    return SemanticFeatures(record_id=digest([sample.sample_id, 'UNSUPPORTED_NATIVE_TASK_BINDING']),
        sample_id=sample.sample_id, extractor_version='contract-only/1', mcp_version=None,
        feature_schema='roblox_project_structural_features/v1', relations=None, features=None,
        quality_flags=['NATIVE_NUMERIC_KERNEL_PRESENT', 'ROBLOX_TASK_BINDING_NOT_IDENTIFIED'],
        known_at=sample.as_of, status='UNSUPPORTED')

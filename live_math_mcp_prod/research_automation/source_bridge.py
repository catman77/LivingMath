"""Read-only projection of the existing public model envelope into research input contracts."""
from collections import defaultdict

from .contract import Fact, Hypothesis, Prediction, Problem, ResearchInput


def public_model_inputs(model: dict, artifact_sha256: str) -> list[ResearchInput]:
    """Preserve nulls and alternative readings; never infer missing physical/model targets."""
    version = model.get('model_version', '')
    if not version.startswith('LM-SUTI-ALCH-006/'):
        raise ValueError('UNSUPPORTED_PUBLIC_SOURCE_ENVELOPE')
    expected = {'material_identity', 'phase', 'physical_time_order', 'actor_identity',
                'physiological_effect', 'translation_or_unclear_glyph_resolution'}
    groups = defaultdict(list)
    for row in model['uncertainty']:
        field = row['payload']['field']
        if field not in expected or row['payload']['value'] is not None:
            raise ValueError('UNKNOWN_SCHEMA_OR_NON_NULL_UNKNOWN_FIELD')
        groups[field].append(row)
    out = []
    for field, rows in sorted(groups.items()):
        scope = 'source/' + artifact_sha256 + '/' + field
        refs = sorted({ref for r in rows for ref in r['source_refs']})
        problem = Problem(kind='input_gap', scope=scope, title=field,
            required_features=[field], source_refs=refs, unknown_refs=[r['record_id'] for r in rows])
        out.append(ResearchInput(scope=scope, artifact_sha256=artifact_sha256,
            origin='PUBLIC_SOURCE_UNKNOWN_CONTRACT', source_refs=refs, problems=[problem]))
    for pair in model['alternatives']['branch_pairs']:
        scope = 'source/' + artifact_sha256 + '/' + pair['fork_id']
        # Both alternatives expose exactly the same source projection. Reading labels are not measured features.
        hypotheses = [Hypothesis(model_id=bid, target=None, predictions=[Prediction(
            feature='source_projection', value=pair['common_source_projection_sha256'])]) for bid in pair['branch_ids']]
        out.append(ResearchInput(scope=scope, artifact_sha256=artifact_sha256, origin='PUBLIC_UNRESOLVED_NONEXCLUSIVE_READINGS',
            source_refs=pair['source_refs'], problems=[Problem(kind='identify_model', scope=scope,
                hypotheses=hypotheses, source_refs=pair['source_refs'])],
            facts=[Fact(feature='source_projection', value=pair['common_source_projection_sha256'], source_refs=pair['source_refs'])]))
    scope = 'source/' + artifact_sha256 + '/text-only'
    problems = [Problem(kind='input_gap', scope=scope, title='Typed source-bound formulation required',
        required_features=['formalization/' + r['payload']['span_id']], source_refs=r['source_refs'])
        for r in model['reverse_traces'] if r['payload']['modeling_status'] == 'TEXT_ONLY']
    if problems:
        out.append(ResearchInput(scope=scope, artifact_sha256=artifact_sha256, origin='PUBLIC_TEXT_ONLY_FORMULATION_GAPS', problems=problems))
    return out

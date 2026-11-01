"""Open synthetic preflight of actual S binding/path generation; not scientific n."""
import json
from pathlib import Path

from artifact_genesis.source import packet_from_text
from .observe import observe, constraints_from_evidence
from .search import enumerate_bindings, generate_queries
from .compiler import compile_model
from .query import evaluate, deletion_witnesses


def preflight() -> dict:
    raw = packet_from_text('open-calibration', 'Methods in diuers manners be doone.\nA implies B.\nB implies C.\nFor such work is not to our intent.\n')
    train = raw.model_copy(update={'spans': raw.spans[:3]})
    context = raw.model_copy(update={'spans': raw.spans[3:]})
    observed = observe(train); family = enumerate_bindings(observed['dimensions'])
    model = compile_model(observed['premises'], family['bindings'][0]); queries = generate_queries(observed['premises'], model)
    outcomes = [evaluate(model, q) for q in queries]
    constraints = constraints_from_evidence(observed, context)
    revised = enumerate_bindings(observed['dimensions'], constraints)
    passed = len(family['bindings']) == 2 and len(revised['bindings']) == 1 and bool(queries) and all(o['value'] for o in outcomes)
    return {'status': 'PASS_SYMBOLIC_CAPABILITY' if passed else 'MISSING_GENERATIVE_CAPABILITY',
            'route_S': 'ACTUALLY_EXECUTED', 'route_L': 'NO_PINNED_EXECUTOR_USED',
            'raw_input': train.model_dump(), 'observations': observed, 'generated_family': family,
            'open_continuation': context.model_dump(), 'constraints': constraints, 'revised_family': revised,
            'generated_queries': queries, 'outcomes': outcomes,
            'premise_deletion_witnesses': deletion_witnesses(observed['premises'], family['bindings'][0], model, queries[0]) if queries else [],
            'hypothesis_authorship': 'SYMBOLIC_SEARCH_FROM_RAW_LOCAL_OBSERVATIONS',
            'rule_and_fixture_authorship': 'CODE_AGENT_IMPLEMENTATION_AND_SYNTHETIC_CALIBRATION',
            'scientific_evidence': False, 'LLM_calls': 0, 'tokens': None, 'human_review': 'NOT_TESTED'}


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(); p.add_argument('--out', type=Path, required=True); a = p.parse_args()
    result = preflight(); a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(result['status'])

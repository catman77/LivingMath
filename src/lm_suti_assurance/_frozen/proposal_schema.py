"""Strict untrusted Delta parsing, not scientific admission."""
from pathlib import Path
import copy
from jsonschema import Draft202012Validator
from common002 import strict_json,load

SCHEMA=load(Path(__file__).with_name('PROPOSAL_DELTA_V1.schema.json'))
KINDS={'FINITE_PROPOSITION':['FINITE_TRACE'],'SOURCE_CLAIM':['SOURCE_PROJECTION','SOURCE_FIELD','SOURCE_PERMISSION'],
    'EXECUTABLE_BOUNDED':['BOUNDED_PROPERTY'],'EMPIRICAL_HYPOTHESIS':['EMPIRICAL_HYPOTHESIS']}


class ProposalError(ValueError):
    def __init__(self,reason: str,stage: str='DELTA_SCHEMA'):
        self.reason,self.stage=reason,stage
        super().__init__(reason)


def parse_delta(raw: str) -> dict:
    try:value=strict_json(raw)
    except (ValueError,TypeError) as exc:
        reason='DUPLICATE_JSON_KEY' if 'DUPLICATE_JSON_KEY' in str(exc) else 'NONFINITE_JSON' if 'NONFINITE_JSON' in str(exc) else 'INVALID_JSON'
        raise ProposalError(reason,'DELTA_PARSE')
    if not Draft202012Validator(SCHEMA).is_valid(value):raise ProposalError('MODEL_DELTA_INVALID')
    return value


def transport_schema(task: dict) -> dict:
    # Narrow only by trusted task domain. Both false semantic alternatives remain.
    branches=[]
    for branch in SCHEMA['oneOf']:
        kind=branch['properties'].get('kind',{}).get('const')
        if kind is None or kind in KINDS[task['claim_kind']]:branches.append(copy.deepcopy(branch))
    return {'oneOf':branches}

"""Separate opt-in contracts; all historical schemas remain untouched."""
import copy
from ..core import canonical
from ..symbolic.contracts import REQUEST as LEGACY, LIMITS, validate as legacy_validate
from ..symbolic.state import require
from ..white_star.contracts import check_schema

SYMBOLIC_POLICY = 'frontier_argument_coverage_v1'
NUMERIC_POLICY = 'cat_distinction_tiebreak_v1'
SYMBOLIC_REQUEST = copy.deepcopy(LEGACY)
SYMBOLIC_REQUEST['properties']['search']['properties']['strategy'] = {'const': SYMBOLIC_POLICY}
SYMBOLIC_REQUEST['properties']['search']['properties']['cpu_budget_ms'] = {'type': 'integer', 'minimum': 1, 'maximum': 4000}
# This structural explorer does not induce grammars or consume labels.
SYMBOLIC_REQUEST['properties']['task']['properties'] = {
    'mode': {'enum': ['discover_relations', 'descriptive']}, 'max_rules': {'type': 'integer', 'minimum': 1, 'maximum': 15}}


def validate(request):
    check_schema(request, SYMBOLIC_REQUEST)
    clone = copy.deepcopy(request)
    clone['search'].pop('cpu_budget_ms',None)
    clone['search']['strategy'] = 'local_structural_novelty'
    legacy_validate(clone)
    require(len(canonical(request).encode()) <= LIMITS['request_bytes'], 'INPUT_TOO_LARGE')
    from ..symbolic.state import History,source_states
    source_states(request,History())
    return request

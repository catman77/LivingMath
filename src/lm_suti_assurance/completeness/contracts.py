"""Additive, bounded transport; legacy White Star contracts are unchanged."""
import copy
import hashlib
from pathlib import Path
from ..core import digest
from ..symbolic.contracts import obj, integer, PROJECT, KEY, REF
from ..white_star.contracts import TOOLS as OLD_TOOLS, check_schema, preflight
from ..symbolic.state import require

OBSERVER = 'pair-sign-and-absolute-dominance/1'
SCOPE = {'mode': 'completeness_only', 'observer': OBSERVER}
ORIGIN = 'CONSTRUCTED_CERTIFIED_WITNESS'
SCOPE_SCHEMA = obj({'mode': {'const': SCOPE['mode']}, 'observer': {'const': OBSERVER}}, list(SCOPE))
CURSOR = obj({'plan_ref': REF, 'index': integer(0, 16128), 'prefix_sha256': REF}, ['plan_ref', 'index', 'prefix_sha256'])
COMMON = {'project': PROJECT, 'plan_ref': REF}
TOOLS = {
    'coverage_plan': obj({'project': PROJECT, 'request_key': KEY, 'source_request': copy.deepcopy(OLD_TOOLS['white_star_explore']['inputSchema']['properties']['request']), 'scope': SCOPE_SCHEMA}, ['project', 'request_key', 'source_request', 'scope']),
    'coverage_advance': obj({**COMMON, 'request_key': KEY, 'cursor': CURSOR, 'work_budget': integer(0, 128)}, ['project', 'plan_ref', 'request_key', 'cursor', 'work_budget']),
    'coverage_inspect': obj({**COMMON, 'view': {'enum': ['summary', 'plan', 'atlas', 'omissions', 'records', 'delivery']}, 'cursor': integer(0, 16128), 'page_size': integer(1, 128), 'acknowledgement': obj({'export_sha256': REF, 'record_count': integer(0, 16128), 'client_id': {'type': 'string', 'minLength': 1, 'maxLength': 128}}, ['export_sha256', 'record_count', 'client_id']), 'request_key': KEY}, ['project', 'plan_ref']),
    'coverage_replay': obj({**COMMON, 'cursor': integer(0, 16128), 'work_budget': integer(1, 128)}, ['project', 'plan_ref']),
}


def validate(request: dict, scope: dict) -> None:
    check_schema(scope, SCOPE_SCHEMA)
    preflight(request)
    require(request.get('atlas_profile', 'cj_v1') == 'cj_v1', 'COVERAGE_REQUIRES_CJ_V1')


def kernel_binding() -> dict:
    """Both the integer primitive and the new checker/dispatcher are pinned."""
    from ..white_star.contracts import integrity, VENDOR
    files = integrity()
    files['integration/white_star_adapter.py'] = hashlib.sha256((VENDOR/'integration/white_star_adapter.py').read_bytes()).hexdigest()
    for name in ('contracts.py', 'planner.py', 'verify.py', 'worker.py'):
        files['completeness/' + name] = hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
    return {'sha256': digest(files), 'files': files, 'integer_backend': 'SUPPLIED_PYTHON_CAD_PROJECT', 'native_phase': 'AUXILIARY_NOT_COVERAGE_PROOF'}

"""Frozen local evaluation and real read-only MCP boundary checks."""
import copy
import json
import resource
import time
from pathlib import Path

from . import __version__
from .audit import audit
from .canonical import Refusal, bytes_hash, canonical_hash, read_json, statuses
from .demos import independent_oracles
from .intake import ROOT, intake
from .journal import append
from .lm_client import ReadOnlyClient, connect, payload
from .mapping import candidates, fingerprint, project
from .reverse import reverse
from .scoring import score


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def frozen_inputs() -> dict:
    freeze = read_json(ROOT / 'eval/preregistration.json')
    for name, digest in freeze['files'].items():
        if bytes_hash((ROOT / name).read_bytes()) != digest:
            raise Refusal('PREREGISTRATION_DRIFT', name)
    return freeze


def load_fixture(family: str) -> tuple[dict, bytes]:
    env = read_json(ROOT / 'fixtures' / (family + '.json'))
    raw = (ROOT / 'fixtures' / (family + '.txt')).read_bytes()
    return env, raw


def run_local(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    started, cpu = time.perf_counter_ns(), time.process_time_ns()
    freeze = frozen_inputs()
    settings = read_json(ROOT / 'eval/settings.json')
    trust = read_json(ROOT / 'fixtures/trust.json')
    branches, controls, local_tasks = [], [], []
    for family in ('poetry', 'pythagoras', 'boa'):
        env, raw = load_fixture(family)
        accepted = intake(env, raw, trust)
        interpretations = candidates(env, family)
        assert len({fingerprint(c) for c in interpretations}) == 2
        for candidate in interpretations:
            projection = project(env, candidate, settings)
            audited = audit(env, projection, settings, source_bytes=raw, trust=trust)
            assert audited['status'] == 'PASS_DECLARED_STRUCTURE', audited
            reversed_result = reverse(env, projection, audited)
            record = {'family': family, 'intake': accepted, 'input_contract': env,
                      'candidate': candidate, 'projection': projection, 'audit': audited, 'reverse': reversed_result}
            branches.append(record)
            append(out / 'journal.jsonl', 'independent_interpretation', {'envelope': env, 'candidate': candidate}, record)
            damaged = copy.deepcopy(projection)
            damaged['bindings'][0]['declared_statement'] = 'Intentionally distorted meaning; this is not the source declaration.'
            negative = audit(env, damaged, settings, source_bytes=raw, trust=trust)
            controls.append({'family': family, 'candidate': candidate['id'], 'control': 'DISTORTED_SOURCE_DECLARATION',
                             'input': damaged, 'output': negative, 'result': 'PASS' if negative['status'] == 'REFUSED' else 'FAIL'})
            append(out / 'journal.jsonl', 'negative_evidence', damaged, negative)
        rename = copy.deepcopy(interpretations[0]);rename['id'] = 'renamed';rename['title'] = 'Novel label'
        controls.append({'family': family, 'control': 'RENAME_ONLY_NOT_NOVEL',
                         'result': 'PASS' if fingerprint(rename) == fingerprint(interpretations[0]) else 'FAIL'})
    oracles = independent_oracles(settings)
    for card in read_json(ROOT / 'eval/tasks.json'):
        local_tasks.append({'task_id': card['id'], 'local_check': 'FINITE_FIXTURE_CHECKED' if card['fixture'] else 'NOT_TESTED_NO_AUTHOR_SOURCE',
                            'comparison_status': 'INCONCLUSIVE', 'author_status': 'AUTHOR_REVIEW_NOT_AVAILABLE',
                            'arms': card['arms'], 'arm_order': card['arm_order'], 'equal_budget': card['identical_budget']})
    result = {'status': 'PASS_LOCAL_PROTOCOL_PROTOTYPE', 'version': __version__,
              'P0': 'PASS', 'P1': 'PASS_DECLARED_FINITE_MODELS', 'P3': 'PARTIAL_EVALUATION',
              'REAL_SUTI_INTEGRATION': 'NOT_TESTED', 'AUTHOR_ACCEPTANCE': 'INCONCLUSIVE',
              'BASELINE_ADVANTAGE': 'NOT_ESTABLISHED', 'MATHEMATICAL_ORIGINALITY': 'NOT_ESTABLISHED',
              'preregistration_sha256': canonical_hash(freeze), 'interpretations': len(branches),
              'negative_controls': len(controls), 'oracles': oracles,
              'metrics': score(branches),
              'cost': {'wall_ns': time.perf_counter_ns() - started, 'cpu_ns': time.process_time_ns() - cpu,
                       'peak_RSS_KiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                       'LLM_calls': 0, 'LLM_model': None, 'LLM_tokens': 0, 'API_spend': 0, 'LM_native_calls': 0},
              **statuses(semantic='DECLARED_STRUCTURE_PRESERVED', mathematical='FINITE_MODEL_CHECKED',
                         execution='LOCAL_DEMOS_COMPLETED', unknowns=['Real SUTI export/import, author agreement, independent blind review and paired LLM baseline are unavailable.'])}
    assert all(c['result'] == 'PASS' for c in controls)
    assert oracles['boa_inverse_all_65536_pairs'] and oracles['first_order_collision']
    assert all(oracles['pythagorean_checks'].values()) and oracles['poetry_noncommutative_in_declared_model']
    for name, value in [('branches.json', branches), ('negative-controls.json', controls),
                        ('tasks-local.json', local_tasks), ('result.json', result)]:
        write(out / name, value)
    return result


async def run_live(out: Path, endpoint: str, token_file: Path, project_id: str) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter_ns()
    checks = []
    def check(name, okay, detail=None):
        row = {'check': name, 'result': 'PASS' if okay else 'FAIL', 'detail': detail}
        checks.append(row)
        write(out / 'checks.json', checks)
        if not okay:
            write(out / 'first-failure.json', row)
            raise AssertionError(row)
    async with connect(endpoint, token_file, out / 'mcp-wire.jsonl') as session:
        init = await session.initialize();catalog = await session.list_tools()
        write(out / 'tools-list.json', {'initialize': init.model_dump(mode='json'), 'list': catalog.model_dump(mode='json')})
        check('installed_initialize_020_and27', init.serverInfo.version == '1.0.0rc1' and len(catalog.tools) == 27)
        client = ReadOnlyClient(session, catalog.model_dump(mode='json'), {project_id})
        health = payload(await client.call('service_health', {}))
        contract = payload(await client.call('research_contract', {}))
        check('health_installed_release', health.get('installed_release', {}).get('version') == '1.0.0rc1')
        check('ledger042_is_not_regression', health.get('version') == '0.4.2' and health.get('schema_version') == 5)
        check('protocol019', contract.get('installed_release', {}).get('protocol') == 'livingmath-research019/v1')
        check('audit_ok', health.get('audit', {}).get('ok') is True)
        context = payload(await client.call('research_context', {'project': project_id, 'limit': 1}))
        check('new_QA_project_empty', context.get('events') == [])
        normal_response = await client.call('research_normalize_preview', {'project': project_id,
            'focus': 'Bridge read-only metadata probe; no source text sent.', 'source_event_ids': [], 'query_scope': {'level': 'C2'}})
        normal = payload(normal_response)
        check('normalization_explicit_missing_source_refusal', normal_response.get('isError') is True
              and 'source_event_ids' in normal.get('message', '') and 'at least 1' in normal.get('message', ''),
              {'classification': 'EXPECTED_REFUSAL_NO_REGISTERED_SOURCE', 'source_contract_schema_gap': 'Advertised schema lacks runtime minItems=1.'})
        source = await client.call('research_source_contract', {'project': project_id})
        check('source_explicitly_not_registered', source.get('isError') is True
              and 'SOURCE_CONTRACT_NOT_REGISTERED' in payload(source).get('message', ''))
        for family in ('poetry', 'pythagoras', 'boa'):
            env, _ = load_fixture(family)
            refused = client.native_preview(env)
            check(family + '_native_explicitly_unsupported', refused['status'] == 'UNSUPPORTED_SOURCE' and not refused['native_call_sent'])
        for name, args in [('record_result', {'project': project_id}), ('transition_research_move', {'project': project_id}),
                           ('research_cycle_precommit', {'request': {'project': project_id}}),
                           ('research_context', {'project': 'RH'}), ('research_context', {'project': project_id + '_OTHER'})]:
            before = len(client.calls)
            try:
                await client.call(name, args)
            except Refusal:
                check('blocked_before_transport:' + name + ':' + args.get('project', 'nested'), len(client.calls) == before)
            else:
                check('blocked_before_transport:' + name, False)
        write(out / 'mcp-calls.json', client.calls)
        write(out / 'health.json', health);write(out / 'contract.json', contract)
        result = {'status': 'PASS_READ_ONLY_MCP_BOUNDARY', 'endpoint': endpoint, 'checks': len(checks),
                  'MCP_tool_calls': len(client.calls), 'production_research_writes': 0,
                  'source_content_uploaded': False, 'LM_native_executions': 0,
                  'preview_execution': 'NOT_TESTED_NO_REGISTERED_BRIDGE_ADAPTER',
                  'normalization': 'EXPECTED_MISSING_SOURCE_REFUSAL',
                  'known_server_contract_gaps': ['normalize schema misses minItems=1',
                      'Query017 accepted by advertised cycle schema is rejected by legacy route for BRIDGE_QA project; prior cohort retained'],
                  'wall_ns': time.perf_counter_ns() - start, **statuses(execution='READ_ONLY_MCP_COMPLETED')}
        write(out / 'result.json', result)
        return result

import asyncio
import copy
import json
from pathlib import Path
import sys

from mcp import ClientSession
import pytest

from research_store import ResearchStore
from research_cycle009 import material, validate_completion, validate_executable_readout
from research_cycle009 import qa_closure_changes
from research_cycle009_worlds import declarations, environments
from research_cycle009_oracle import rank, sequence, signatures
from research_cycle009_transport import measured_stdio
from research_cycle009_runtime import Cycle
from qa_positive_acceptance import snapshot


@pytest.mark.parametrize('index', range(3))
def test_frozen_world_genuinely_changes_T_after_negative_feedback(index):
    world = declarations('UNIT009')[index]
    env = environments([world], ['unit-salt-never-shared'])[0]
    oracle = sequence(world, env)
    assert len(oracle['steps'][0]['active_before']) == 3
    assert len(oracle['steps'][0]['active_after']) == 2
    assert len(oracle['steps'][1]['active_after']) == 1
    assert oracle['steps'][0]['attention']['test_id'] != oracle['steps'][1]['attention']['test_id']
    assert oracle['steps'][0]['outcome'] == 'FAILURE'
    assert oracle['steps'][1]['outcome'] == 'SUCCESS'
    assert oracle['final_attention']['status'] == 'NO_INFORMATIVE_TEST'


def test_no_hidden_environment_or_oracle_in_source_declarations():
    values = declarations('UNIT009')
    text = json.dumps(values)
    assert not any(key in text for key in ('target_word', 'measurement', 'oracle_answer', 'raw_signatures'))
    # "instrument_policy" describes an experiment, not future observations.
    assert all('parameters' in w and 'histories' in w and len(w['histories']) == 3 for w in values)


def test_material_equality_does_not_drop_provenance_or_native_work():
    value = {'cold_wall_ns': 3, 'source_hashes': [{'sha256': 'real'}], 'cost_ledger': {'native': 4, 'interpretation_ns': 5}}
    assert material(value) == {'source_hashes': [{'sha256': 'real'}], 'cost_ledger': {'native': 4}}


def test_premise_only_or_foreign_event_cannot_complete_measurement():
    world = declarations('UNIT009')[0]
    binding = {'version': 1}
    result = {'outcome': 'FAILURE', 'data': {'readout': {'observation': 1}}}
    event = {'project': world['project'], 'content': json.dumps({'claim_type': 'SOURCE_CLAIM'})}
    with pytest.raises(ValueError, match='ACTUAL_MATCHING_MEASUREMENT'):
        validate_completion(event, world, binding, 't1', result)
    with pytest.raises(ValueError, match='FOREIGN'):
        validate_completion({**event, 'project': 'FOREIGN'}, world, binding, 't1', result)


def test_permission_only_readout_is_not_an_executable_discriminator():
    world = declarations('UNIT009')[0]
    test = {'test_id': 't1', 'suffix': ['a1'], 'cost': 0, 'ordinal': 1,
            'counterfactuals': [{'readout': {'defined': False, 'admissibility': [False]}}]}
    with pytest.raises(ValueError, match='PERMISSION_ONLY'):
        validate_executable_readout(world, test, {'test_id': 't1'})


def test_actual_MCP_stdio_preserves_DB_and_collects_whole_process_exit_cost(tmp_path):
    db = tmp_path / 'qa.sqlite3'; ResearchStore(db)
    before = snapshot(db)
    out = tmp_path / 'session'
    async def exercise():
        async with measured_stdio(db, out) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.version == '0.4.2'
                tools = await session.list_tools()
                assert len(tools.tools) == 20
                response = await session.call_tool('service_health', {})
                assert not response.isError
    asyncio.run(exercise())
    assert snapshot(db) == before
    receipt = json.loads((out / 'server-exit-usage.json').read_text())
    assert receipt['returncode'] == 0
    assert receipt['CPU_ns_inclusive_descendants'] > 0 and receipt['peak_rss_KiB'] > 0


def test_QA_cleanup_uses_existing_closed_status_through_real_MCP(tmp_path):
    db = tmp_path / 'qa.sqlite3'; store = ResearchStore(db)
    event = store.record('LM_QA_CYCLE009_STATUS', 'experiment', 'QA result', 'Finite test ended.', 'experiment')
    obligation = store.frontier.create('LM_QA_CYCLE009_STATUS', 'Finite QA work', 'status-test', [event['id']])
    async def exercise():
        async with measured_stdio(db, tmp_path / 'status-session') as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.call_tool('research_obligation_update', {'project': 'LM_QA_CYCLE009_STATUS',
                    'obligation_id': obligation['id'], 'expected_version': 1, 'changes': qa_closure_changes(event['id'])})
                assert not response.isError, response
                out = response.structuredContent or json.loads(response.content[0].text)
                assert out['status'] in {'RESOLVED', 'REFUTED', 'SUPERSEDED'}
                assert out['proof_status'] == 'unverified'
    asyncio.run(exercise())


def test_repeated_I_preview_uses_seen_distinction_history_through_MCP(tmp_path):
    db = tmp_path / 'qa.sqlite3'; ResearchStore(db)
    cycle = Cycle(tmp_path, db, tmp_path.parent / 'never-used-production.sqlite3')
    world = declarations('UNIT009_NOVELTY')[0]
    async def exercise():
        async with measured_stdio(db, tmp_path / 'novelty-session') as (read, write):
            async with ClientSession(read, write) as session:
                cycle.client = session; await session.initialize()
                binding = await cycle.seed(world, '0' * 64)
                first = await cycle.preview(world, binding, 'novelty-first')
                repeat = await cycle.preview(world, binding, 'novelty-repeat')
                assert first['status'] == 'NEW_DISTINCTION'
                assert repeat['status'] == 'NO_NEW_DISTINCTION_BOUNDED'
                assert repeat['interpretation']['reason'] == 'SEEN_STRUCTURAL_DISTINCTION'
                assert first['attention']['ranking'] == repeat['attention']['ranking']
    asyncio.run(exercise())

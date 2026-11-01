import asyncio
import copy
import json
from pathlib import Path
import sqlite3
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from native_preview008_contract import NativeRequest, NormalizeRequest
from native_preview008_engine import install_readonly_sqlite
from native_preview008_fixtures import ORIGINAL007, changed, materialize_copy, native_request, normalize_request
from native_preview008_server import PreviewBoundary
from qa_positive_acceptance import snapshot


@pytest.fixture
def world():
    return json.loads((ORIGINAL007 / 'worlds.json').read_text())[0]


@pytest.mark.parametrize('fault', ['wrong_law', 'guard_false', 'partial_law', 'stale_law', 'closed',
                                  'long_suffix', 'invalid_suffix', 'source_code', 'point_germ'])
def test_native_source_faults_fail_closed_or_bounded_fallback(tmp_path, world, fault):
    w = changed(world, fault)
    db = materialize_copy(w, tmp_path / 'source')
    before = snapshot(db)
    out = PreviewBoundary(db).run('native', native_request(w))
    assert not out['execution_permission']['allowed'] and out['proof_status'] == 'unverified'
    if fault in {'wrong_law', 'guard_false', 'partial_law', 'stale_law'}:
        assert out['status'] == 'NEW_DISTINCTION', out
        assert out['interpretation']['strategy'] == 'FALLBACK_BOUNDED'
    else:
        assert out['status'] == 'INSUFFICIENT_CONTEXT', out
    assert snapshot(db) == before


@pytest.mark.parametrize('mutation', ['foreign', 'missing', 'hash', 'stale', 'adapter', 'observer', 'C4', 'budget'])
def test_request_guards_are_readonly(tmp_path, world, mutation):
    db = materialize_copy(world, tmp_path / 'source')
    request = native_request(world)
    if mutation == 'foreign': request['project'] = 'OTHER'
    if mutation == 'missing': request['source_event_ids'][0] = 999999
    if mutation == 'hash': request['source_bindings'][0]['sha256'] = '0' * 64
    if mutation == 'stale': request['active_frontier_version'] += 1
    if mutation == 'adapter': request['source_adapter_id'] = '__import__("os")'
    if mutation == 'observer': request['observer']['mod'] = 2
    if mutation == 'C4': request['question']['context_level'] = 'C4'
    if mutation == 'budget': request['budget'] = {'source_bytes': 4096}
    before = snapshot(db)
    out = PreviewBoundary(db).run('native', request)
    assert out['status'] == 'INSUFFICIENT_CONTEXT', out
    assert out['execution_permission'] == {'allowed': False}
    assert snapshot(db) == before


def test_actual_MCP_tools_schema_replay_and_no_writes(tmp_path, world):
    db = materialize_copy(world, tmp_path / 'source')
    before = snapshot(db)
    async def exercise():
        parameters = StdioServerParameters(command=sys.executable,
            args=[str(Path(__file__).with_name('native_preview008_server.py')), '--db', str(db)])
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                listing = await client.list_tools()
                assert {t.name for t in listing.tools} == {'research_normalize_preview', 'research_native_preview'}
                assert all(t.annotations.readOnlyHint and t.inputSchema['additionalProperties'] is False for t in listing.tools)
                answers = []
                for _ in range(2):
                    response = await client.call_tool('research_native_preview', native_request(world))
                    assert not response.isError, response
                    out = response.structuredContent or json.loads(response.content[0].text)
                    assert out['status'] == 'NEW_DISTINCTION', out
                    assert out['witness']['readouts'][0] != out['witness']['readouts'][1]
                    assert out['execution_permission'] == {'allowed': False}
                    answers.append(out['witness'])
                assert answers[0] == answers[1]
                response = await client.call_tool('research_native_preview', {**native_request(world), 'python': 'pass'})
                assert response.isError
                response = await client.call_tool('research_normalize_preview', normalize_request(world, 'C4'))
                assert not response.isError
                out = response.structuredContent or json.loads(response.content[0].text)
                assert out['status'] == 'EXPLANATION_ONLY'
                assert not out['audit_sufficient']
    asyncio.run(exercise())
    assert snapshot(db) == before


def test_hard_deadline_kills_noncooperative_worker(tmp_path, world):
    db = materialize_copy(world, tmp_path / 'source')
    boundary = PreviewBoundary(db)
    worker = tmp_path / 'deliberately_noncooperative.py'
    worker.write_text('while True: pass\n')
    boundary.worker = worker
    request = native_request(world); request['budget']['deadline_ms'] = 100
    start = time.monotonic()
    result = boundary.run('native', request)
    assert result['status'] == 'RESOURCE_LIMIT' and result['reason'] == 'HARD_WORKER_TIMEOUT'
    assert time.monotonic() - start < 2
    assert result['child_usage_status'] == 'OS_WAIT4_THROUGH_EXIT'


def test_cold_cpu_and_memory_use_OS_receipt_through_child_exit(tmp_path, world):
    db = materialize_copy(world, tmp_path / 'source')
    out = PreviewBoundary(db).run('native', native_request(world))
    assert out['child_usage_status'] == 'OS_WAIT4_THROUGH_EXIT'
    assert out['child_cpu_ns'] >= out['worker_total_cpu_ns'] > 0
    assert out['child_peak_rss_KiB'] >= out['worker_max_rss_KiB'] > 0


def test_concurrent_child_CPU_receipts_do_not_use_global_deltas(tmp_path, world):
    from concurrent.futures import ThreadPoolExecutor
    db = materialize_copy(world, tmp_path / 'source')
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(PreviewBoundary(db).run, 'native', native_request(world)) for _ in range(2)]
        results = [job.result() for job in jobs]
    assert all(out['child_usage_status'] == 'OS_WAIT4_THROUGH_EXIT' and
               out['child_cpu_ns'] >= out['worker_total_cpu_ns'] > 0 for out in results)


def test_sql_authorizer_denies_even_audit_request_key_and_schema_writes(tmp_path, world, monkeypatch):
    db = materialize_copy(world, tmp_path / 'source')
    before = snapshot(db)
    original = sqlite3.connect
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, 'connect', original)
        install_readonly_sqlite(db)
        conn = sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True)
        for sql in ["INSERT INTO policies VALUES('X','X',1)", 'DELETE FROM operations',
                    'CREATE TABLE escape(x)', 'PRAGMA user_version=6', 'PRAGMA query_only=OFF',
                    "ATTACH DATABASE ':memory:' AS escape"]:
            with pytest.raises(sqlite3.DatabaseError): conn.execute(sql)
        conn.close()
    assert snapshot(db) == before


@pytest.mark.parametrize('field,value', [('verified', True), ('code', 'pass')])
def test_structured_models_refuse_authority_or_executable_fields(world, field, value):
    request = native_request(world); request['question'][field] = value
    with pytest.raises(ValueError): NativeRequest.model_validate(request)


def test_schema_caps_and_no_implicit_expansion(world):
    request = native_request(world); request['budget']['native_calls'] = 2049
    with pytest.raises(ValueError): NativeRequest.model_validate(request)
    request = normalize_request(world); request['query_scope']['level'] = 'C5'
    with pytest.raises(ValueError): NormalizeRequest.model_validate(request)

"""Real existing OAuth MCP on SQLite BackupAPI clones; no production endpoints."""
import argparse
import json
from pathlib import Path
from typing import Any, cast

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from dav_acceptance import TappedStream
from davcore.ast import implication
from artifact_translation import qa as existing_qa
from artifact_genesis.source import save


async def exercise(url: str, token: str, out: Path, experiment: Path) -> dict:
    checks = []; calls = []; objects = []
    project = 'LM_QA_GROUNDING003'
    hs = [json.loads(x) for x in (experiment / 'proposals.jsonl').read_text().splitlines()]
    reviews = [json.loads(x) for x in (experiment / 'source-critique.jsonl').read_text().splitlines()]
    trials = [json.loads(x) for x in (experiment / 'DAV-witnesses.jsonl').read_text().splitlines()]

    def require(name: str, ok: bool) -> None:
        checks.append({'invariant': name, 'result': 'PASS' if ok else 'FAIL'})
        save(out / 'checks.json', checks)
        if not ok:
            raise AssertionError(name)

    async with httpx.AsyncClient(headers={'Host': 'livingmath.example', 'Authorization': 'Bearer ' + token}, timeout=30) as http:
        async with streamable_http_client(url + '/mcp', http_client=http) as (read, send, _):
            async with ClientSession(cast(Any, TappedStream(read, out / 'mcp-wire.jsonl', 'server_to_client')),
                                     cast(Any, TappedStream(send, out / 'mcp-wire.jsonl', 'client_to_server'))) as session:
                init = await session.initialize(); listing = await session.list_tools()
                save(out / 'initialize.json', init.model_dump(mode='json'))
                save(out / 'tools-list.json', listing.model_dump(mode='json'))
                names = {t.name for t in listing.tools}
                require('ACTUAL_EXISTING_METHODS', {'record_result', 'dav_register_adapter', 'dav_check_law',
                        'dav_export_evidence', 'service_health', 'artifact_translation_history'} <= names)
                require('NO_NEW_GROUNDING_SERVER_METHODS', not any('grounding' in n for n in names))

                async def call(name, arguments, *, error=False):
                    response = await session.call_tool(name, arguments)
                    calls.append({'tool': name, 'arguments': arguments, 'response': response.model_dump(mode='json')})
                    save(out / 'mcp-transcript.json', calls)
                    require('CALL_' + str(len(calls)), bool(response.isError) == error)
                    if error:
                        return response
                    return response.structuredContent if response.structuredContent is not None else json.loads(response.content[0].text)

                for ident in ['e1-order', 'e2-human-roles']:
                    trial = next(t['witness'] for t in trials if t['case_id'] == ident)
                    review = next(r['review'] for r in reviews if r['case_id'] == ident)
                    h = next(x['H'] for x in hs if x['H']['hypothesis_id'] == trial['hypothesis_id'])
                    require('SOURCE_INTERNAL_ONLY_' + ident, review['status'] == 'SOURCE_INTERNAL_SUPPORT'
                            and review['independent_semantic_review'] == 'SEMANTIC_REVIEW_PENDING'
                            and trial['scientific_law_status'] == 'FAIL_TARGET_TAUTOLOGY')
                    source_args = {'project': project, 'kind': 'hypothesis', 'focus': ident,
                                   'result': json.dumps({'H': h, 'source_critique': review}, ensure_ascii=False),
                                   'status': 'hypothesis', 'request_key': 'source-' + ident}
                    event = await call('record_result', source_args)
                    repeated = await call('record_result', source_args)
                    require('SAME_SOURCE_EVENT_ON_REPEAT_' + ident,
                            repeated['id'] == event['id'] and repeated.get('idempotent') is True)
                    registered = await call('dav_register_adapter', {'project': project,
                        'spec': {'kind': 'reaction_network', 'reaction_network': trial['candidate']['network']},
                        'request_key': 'register-' + ident})
                    formula_args = {'project': project, 'registration_id': registered['id'],
                                    'adapter_binding': registered['payload']['binding'],
                                    'formula': trial['formula'], 'persist': True, 'request_key': 'guard-' + ident}
                    guard = await call('dav_check_law', formula_args)
                    require('FINITE_GUARD_NEVER_SOURCE_TRUTH_' + ident,
                            guard['payload']['status'] == 'proved' and guard['payload']['proof_status'] == 'unverified'
                            and guard['payload']['execution_permission'] == {'allowed': False})
                    repeated_guard = await call('dav_check_law', formula_args)
                    require('SAME_DAV_RESULT_ON_REPEAT_' + ident, repeated_guard == guard)
                    counter = await call('dav_check_law', {**formula_args, 'formula': implication('S0', 'One', 'S1', 'One').model_dump(),
                                                          'request_key': 'static-necessity-' + ident})
                    require('NECESSITY_COUNTERMODEL_RETAINED_' + ident,
                            counter['payload']['status'] == 'refuted' and counter['payload']['counterexample']['state'] == 1)
                    revision = await call('record_result', {'project': project, 'kind': 'counterexample',
                        'focus': 'Bounded source/target review ' + ident, 'parent_id': event['id'], 'status': 'experiment',
                        'result': json.dumps({'source_internal_only': True, 'review_id': review['review_id'],
                                              'counterexample_id': counter['id'], 'target_tautology_rejected': True,
                                              'independent_semantic_review': 'SEMANTIC_REVIEW_PENDING'}, ensure_ascii=False),
                        'evidence': 'dav:' + str(counter['id']), 'request_key': 'revision-' + ident})
                    exported = await call('dav_export_evidence', {'project': project, 'evidence_id': counter['id']})
                    require('REAL_REGISTERED_CERTIFICATE_' + ident, exported['certificate_current'])
                    await call('dav_export_evidence', {'project': 'LM_QA_FOREIGN003', 'evidence_id': counter['id']}, error=True)
                    objects.append({'case_id': ident, 'source_event_id': event['id'], 'revision_event_id': revision['id'],
                                    'registration_id': registered['id'], 'guard_evidence_id': guard['id'],
                                    'counterexample_id': counter['id']})
                    if ident == 'e1-order':
                        await call('record_result', {**source_args, 'status': 'verified', 'request_key': 'forbid-verified'}, error=True)
                        await call('record_result', {**source_args, 'result': 'substituted binding under reused key'}, error=True)
                        await call('record_result', {**source_args, 'project': 'LM_QA_FOREIGN003',
                                                    'parent_id': event['id'], 'request_key': 'foreign-parent'}, error=True)
                        await call('dav_check_law', {**formula_args, 'formula': implication('S0', 'One', 'S1', 'Zero').model_dump()}, error=True)
                history = await call('artifact_translation_history', {'project': project, 'limit': 20})
                require('APPEND_ONLY_FULL_DAV_CHAIN', history['integrity']['ok'])
                health = await call('service_health', {})
                save(out / 'health.json', health)
                require('SQLITE_AND_CANONICAL_AUDIT', health['sqlite_integrity'] == 'ok' and health['audit']['ok'])
                save(out / 'object-ids.json', objects)
                return {'status': 'PASS_REAL_PRIVATE_OAUTH_MCP', 'tool_count': len(names), 'calls': len(calls),
                        'checks': checks, 'objects': objects, 'new_methods': 0, 'production_writes': 0,
                        'source_audit': 'LOCAL_DISJOINT_SOURCE_BEFORE_MCP; not a new server semantic endpoint',
                        'proof_status': 'unverified', 'execution_permission': {'allowed': False}}


def run(source001: Path, experiment: Path, private: Path, out: Path, snapshots: Path | None = None) -> dict:
    previous = existing_qa.checks

    async def callback(url, token, destination, entries):
        return await exercise(url, token, destination, experiment)

    existing_qa.checks = callback
    try:
        return existing_qa.run(source001, private, out, snapshots)
    finally:
        existing_qa.checks = previous


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--source001', type=Path, required=True); p.add_argument('--experiment', type=Path, required=True)
    p.add_argument('--private-root', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    p.add_argument('--snapshots', type=Path)
    a = p.parse_args()
    r = run(a.source001.resolve(), a.experiment.resolve(), a.private_root.resolve(), a.out.resolve(),
            a.snapshots.resolve() if a.snapshots else None)
    print(json.dumps({'status': r['status'], 'calls': r['calls'], 'checks': len(r['checks'])}))

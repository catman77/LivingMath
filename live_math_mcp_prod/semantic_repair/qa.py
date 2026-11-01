"""Existing authenticated MCP compatibility; one run, schema-driven pagination."""
import json
from pathlib import Path
from typing import Any, cast

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from dav_acceptance import TappedStream
from artifact_translation import qa as factory
from artifact_genesis.source import save


def schema_limit(schema: dict, preferred: int = 20) -> int:
    upper = schema['properties']['limit']['maximum']
    if type(upper) is not int or upper < 1:
        raise ValueError('INVALID_PUBLISHED_LIMIT')
    return min(preferred, upper)


async def paginate(read_page, schema: dict, preferred: int = 20) -> list[dict]:
    limit = schema_limit(schema, preferred); offset = 0; records = []; seen = set()
    while True:
        page = await read_page(offset, limit)
        if not page['records'] and offset < page['total']:
            raise ValueError('PAGINATION_DROPPED_RECORDS')
        for row in page['records']:
            if row['id'] in seen:
                raise ValueError('PAGINATION_DUPLICATED_RECORD')
            seen.add(row['id']); records.append(row)
        offset += len(page['records'])
        if offset >= page['total']:
            break
    return records


async def exercise(url, token, out, entries, experiment):
    checks = []; calls = []; ids = []
    project = 'LM_QA_REPAIR004'

    def require(name, ok):
        checks.append({'invariant': name, 'result': 'PASS' if ok else 'FAIL'}); save(out/'checks.json', checks)
        if not ok: raise AssertionError(name)

    async with httpx.AsyncClient(headers={'Host': 'livingmath.example', 'Authorization': 'Bearer '+token}, timeout=30) as http:
        async with streamable_http_client(url+'/mcp', http_client=http) as (read, send, _):
            async with ClientSession(cast(Any, TappedStream(read, out/'mcp-wire.jsonl', 'server_to_client')),
                                     cast(Any, TappedStream(send, out/'mcp-wire.jsonl', 'client_to_server'))) as session:
                init = await session.initialize(); listing = await session.list_tools()
                save(out/'initialize.json', init.model_dump(mode='json')); save(out/'tools-list.json', listing.model_dump(mode='json'))
                schemas = {t.name: t.inputSchema for t in listing.tools}
                require('ACTUAL_EXISTING_SCHEMA', {'record_result','dav_register_adapter','dav_check_law','artifact_translation_history'} <= schemas.keys())
                require('NO_NEW_PUBLIC_TOOL', not any('repair004' in n for n in schemas))

                async def call(name, args, error=False):
                    response = await session.call_tool(name, args)
                    calls.append({'tool': name, 'arguments': args, 'response': response.model_dump(mode='json')}); save(out/'mcp-transcript.json', calls)
                    require('CALL_'+str(len(calls)), bool(response.isError) == error)
                    if error: return response
                    return response.structuredContent if response.structuredContent is not None else json.loads(response.content[0].text)

                family = json.loads((experiment/'binding-families.jsonl').read_text().splitlines()[0])
                args = {'project': project, 'kind': 'hypothesis', 'focus': 'Conditional binding family004',
                        'result': json.dumps(family, ensure_ascii=False), 'status': 'hypothesis', 'request_key': 'conditional-family'}
                event = await call('record_result', args); again = await call('record_result', args)
                require('IDEMPOTENT_H_NOT_FACT', event['id'] == again['id'] and event['status'] == 'hypothesis')
                family_rows = [json.loads(x) for x in (experiment/'binding-families.jsonl').read_text().splitlines()]
                ambiguous = next(x for x in family_rows if x['phase']=='INITIAL' and len(x['family']['bindings'])>1)
                conditional = await call('record_result', {**args, 'focus':'Unresolved conditional family004',
                    'result':json.dumps(ambiguous,ensure_ascii=False),'request_key':'ambiguous-family'})
                require('MULTIPLE_CONDITIONAL_BINDINGS_STAY_HYPOTHESES', conditional['status']=='hypothesis'
                        and all(b['status']=='HYPOTHESIS' for b in ambiguous['family']['bindings']))
                source_revision = next(json.loads(x) for x in (experiment/'revisions.jsonl').read_text().splitlines()
                                       if json.loads(x)['source_constraints'])
                revision_event = await call('record_result', {'project':project,'kind':'counterexample','focus':'Source scope revision004',
                    'result':json.dumps({'task_id':source_revision['task_id'],'source_constraints':source_revision['source_constraints'],
                                         'old_family':source_revision['old_family'],'new_family':source_revision['new_family']},ensure_ascii=False),
                    'status':'experiment','parent_id':conditional['id'],'request_key':'source-scope-revision'})
                await call('record_result', {**args, 'status': 'verified', 'request_key': 'forbid-verified'}, True)
                await call('record_result', {**args, 'result': 'changed under same key'}, True)
                await call('record_result', {**args, 'project': 'LM_QA_OTHER004', 'parent_id': event['id'], 'request_key': 'foreign-parent'}, True)
                models = [json.loads(x) for x in (experiment/'model-commitments.jsonl').read_text().splitlines()]
                queries = [json.loads(x) for x in (experiment/'query-commitments.jsonl').read_text().splitlines()]
                first = next(x for x in queries if x['queries'])
                model = next(x['models'][0] for x in models if x['task_id'] == first['task_id'])
                reg = await call('dav_register_adapter', {'project': project, 'spec': model['spec'], 'request_key': 'compositional-model'})
                law_args = {'project': project, 'registration_id': reg['id'], 'adapter_binding': reg['payload']['binding'],
                            'formula': first['queries'][0]['formula'], 'persist': True, 'request_key': 'composition-law'}
                law = await call('dav_check_law', law_args)
                require('SCOPED_COMPOSITION_NO_GRANT', law['payload']['status'] == 'proved' and law['payload']['proof_status'] == 'unverified'
                        and law['payload']['execution_permission'] == {'allowed': False})
                require('DAV_REPEAT_NO_DUPLICATE', law == await call('dav_check_law', law_args))
                exported = await call('dav_export_evidence', {'project': project, 'evidence_id': law['id']})
                require('REAL_CERTIFICATE_AND_ROW_HASH', exported['certificate_current'] and bool(exported['record']['entry_hash']))
                await call('dav_export_evidence', {'project': 'LM_QA_OTHER004', 'evidence_id': law['id']}, True)
                # Calibration proposals only: actual history rows to exercise multiple pages.
                for i, entry in enumerate(entries[:5]):
                    p = await call('artifact_translation_propose', {'project': project,
                        'request': {'graph': entry['graph'], 'max_candidates': 1, 'allowed_edits': ['catalytic']}, 'request_key': 'pagination-'+str(i)})
                    ids.append({'id': p['id'], 'entry_hash': p['entry_hash']})
                    require('CALIBRATION_PROPOSAL_NO_AUTHORITY_'+str(i), p['payload']['execution_permission'] == {'allowed': False})

                async def page(offset, limit):
                    return await call('artifact_translation_history', {'project': project, 'offset': offset, 'limit': limit})
                rows = await paginate(page, schemas['artifact_translation_history'], preferred=2)
                require('PAGINATION_ALL_ACTUAL_IDS_AND_HASHES', [(r['id'], r['entry_hash']) for r in rows] == [(r['id'], r['entry_hash']) for r in ids])
                health = await call('service_health', {}); save(out/'health.json', health)
                require('SQLITE_AND_AUDIT', health['sqlite_integrity'] == 'ok' and health['audit']['ok'])
                save(out/'object-ids.json', {'source_event': event['id'], 'conditional_family_event':conditional['id'],
                    'source_revision_event':revision_event['id'],'registration': reg['id'], 'evidence': law['id'], 'history_records': ids})
                return {'status': 'PASS_REAL_PRIVATE_OAUTH_MCP', 'calls': len(calls), 'checks': checks, 'tools': len(schemas),
                        'schema_limit': schema_limit(schemas['artifact_translation_history']), 'pagination_rows': rows,
                        'history_calibration_not_scientific_n': True, 'proof_status': 'unverified', 'production_writes': 0}


def run(source001: Path, experiment: Path, private: Path, out: Path, snapshots: Path | None = None) -> dict:
    old = factory.checks
    async def callback(url, token, dest, entries): return await exercise(url, token, dest, entries, experiment)
    factory.checks = callback
    try: return factory.run(source001, private, out, snapshots)
    finally: factory.checks = old

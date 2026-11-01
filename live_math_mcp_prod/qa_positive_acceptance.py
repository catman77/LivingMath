"""Live v0.4.2 QA, isolated by project; capture full MCP JSON-RPC bodies.

Uses the existing local server.env and owner OAuth login. A source-hash-guarded
operator import installs one QA-only constraint. No deployed code is changed.
"""
import argparse
import asyncio
import base64
from contextlib import closing
from datetime import datetime, timezone, timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import shlex
import sqlite3
from urllib.parse import parse_qs, urlparse

import httpx
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client

from frontier import fingerprint_hash
from research_store import ResearchStore
from qa_v042_cases import V042Cases


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def snapshot(db):
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        names = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {'inode': db.stat().st_ino, 'tables': {name: [dict(row) for row in connection.execute(
            'SELECT * FROM "' + name + '" ORDER BY rowid')] for name in names}}


class Acceptance(V042Cases):
    def __init__(self, out, db, origin):
        self.out, self.db, self.origin = out, db, origin
        self.project = 'LM_QA_POS_' + out.name
        self.calls, self.checks, self.ids, self.moves = [], [], {}, []
        self.endpoint = origin + '/mcp'
        self.fixture = b'LivingMath v0.4.2 bounded QA\n'
        self.fixture_hash = hashlib.sha256(self.fixture).hexdigest()
        self.scope = ('Read-only byte_length, sha256, lf_count and byte_sum of the immutable QA fixture '
                      + self.fixture_hash + '; bounded software error controls and diagnosis of cited QA failures only; '
                      'no other data, source transformations or proof claims.')
        self.representation = 'qa_fixture_bytes:' + self.fixture_hash
        (out / 'fixture.bin').write_bytes(self.fixture)
        self.wire = out / 'mcp-wire.jsonl'

    def check(self, name, condition, detail=''):
        self.checks.append({'invariant': name, 'result': 'PASS' if condition else 'FAIL',
                            'detail': detail, 'after_call': len(self.calls)})
        write_json(self.out / 'checks.json', self.checks)

    def wire_log(self, entry):
        with self.wire.open('a') as stream:
            stream.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), **entry}, ensure_ascii=False) + '\n')

    async def request_hook(self, request):
        if str(request.url) == self.endpoint and request.method == 'POST':
            self.wire_log({'direction': 'request', 'body': json.loads(request.content)})

    async def response_hook(self, response):
        if str(response.request.url) == self.endpoint and response.request.method == 'POST':
            body = await response.aread()
            self.wire_log({'direction': 'response', 'http_status': response.status_code,
                           'body': json.loads(body) if body else None})

    async def call(self, name, arguments, allow_error=False):
        operations_before=self.operation_count()
        response = await self.session.call_tool(name, arguments)
        raw = response.model_dump(mode='json')
        self.calls.append({'index': len(self.calls) + 1, 'tool': name, 'arguments': arguments, 'response': raw})
        write_json(self.out / 'calls.json', self.calls)
        if response.isError:
            if allow_error:
                return None
            raise RuntimeError(name + ': ' + ''.join(item.text for item in response.content if item.type == 'text'))
        answer=response.structuredContent if response.structuredContent is not None else json.loads(response.content[0].text)
        if isinstance(answer,dict) and answer.get('idempotent') is True:
            self.check('idempotency:call_'+str(len(self.calls))+':no_new_operations',
                       self.operation_count()==operations_before)
        return answer

    async def event(self, name, result, kind='experiment', status='experiment', parent=True):
        request = {'project': self.project, 'kind': kind, 'status': status,
                   'focus': 'Isolated QA: ' + name, 'result': json.dumps(result, ensure_ascii=False, sort_keys=True),
                   'request_key': self.project + ':event:' + name}
        if parent:
            request['parent_id'] = self.ids['source_event']
        answer = await self.call('record_result', request)
        self.ids[name] = answer['id']
        return answer['id']

    def proposal(self, observable, expected, optional=True):
        move = {'active_frontier_id': self.ids['obligation'], 'active_frontier_version': self.frontier_version,
                'scope': self.scope, 'parent_event_ids': [self.ids['source_event']],
                'proposed_operation': {'mechanism': 'qa_bounded_measurement', 'intent': 'experiment',
                    'premises': ['Use only immutable fixture ' + self.fixture_hash],
                    'mathematical_properties': [observable],
                    'testable_consequence': observable + ' = ' + str(expected),
                    'required_evidence': ['Recorded QA ' + observable + ' measurement']},
                'source_representation': self.representation, 'target_representation': self.representation,
                'verification_plan': {'method': 'Read fixed fixture bytes and compute ' + observable,
                                      'failure_condition': 'Fixture SHA-256 differs or measured value differs from the declared value'}}
        if optional:
            move.update(proposal='QA bounded ' + observable, evidence_refs=['event:' + str(self.ids['source_event'])],
                        preserved_properties={}, claimed_new_distinction={})
        return move

    async def propose(self, name, move):
        answer = await self.call('record_research_move', {'project': self.project, 'move': move,
                                                        'request_key': self.project + ':propose:' + name})
        self.ids[name] = answer['id']
        if answer['id'] not in self.moves:
            self.moves.append(answer['id'])
        return answer

    async def audit(self, name, move_id):
        return await self.call('audit_research_move', {'project': self.project, 'move_id': move_id,
                                                     'request_key': self.project + ':audit:' + name})

    async def transition(self, name, move_id, action, allow_error=False, **kwargs):
        return await self.call('transition_research_move', {'project': self.project, 'move_id': move_id,
            'action': action, 'request_key': self.project + ':' + name, **kwargs}, allow_error)

    async def history(self, move_id):
        return await self.call('research_move_history', {'project': self.project, 'move_id': move_id})

    async def complete(self, name, move_id, observable, measured, outcome='SUCCESS'):
        result_id = await self.event(name + '_result', {'fixture_sha256': self.fixture_hash,
            'observable': observable, 'measured': measured, 'software_qa_only': True,
            'artifact': 'artifact:measurements.json', 'outcome':outcome,'mathematical_status': 'unverified'},
            kind='failed_check' if outcome=='FAILURE' else 'experiment')
        result={'outcome':outcome,'summary':'QA '+observable+' outcome recorded; no proof conclusion.',
                'data':{'observable':observable,'measured':measured,'fixture_sha256':self.fixture_hash}}
        return await self.transition(name + ':complete', move_id, 'complete',
            evidence_refs=['event:' + str(result_id), 'artifact:measurements.json'],
            result=result,
            reason='Measured ' + observable + '=' + str(measured) + ' on the fixed fixture; software acceptance check finished, no proof claim.')

    def seed(self):
        with closing(sqlite3.connect(self.db.as_uri() + '?mode=ro', uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            source = dict(connection.execute('SELECT * FROM events WHERE id=?', (self.ids['source_event'],)).fetchone())
        blueprint = {'import_key': self.project + ':scoped-constraint', 'project': self.project,
            'sources': [{'id': source['id'], 'sha256': fingerprint_hash(source)}],
            'obligations': [{'key': 'qa', 'statement': 'Measure only the fixed QA fixture with qa_bounded_measurement.',
                'scope': self.scope, 'source_event_ids': [source['id']], 'evidence_refs': ['event:' + str(source['id'])]}],
            'constraints': [{'kind': 'allowed_experiment', 'obligation_key': 'qa',
                'mechanisms': ['qa_bounded_measurement'], 'source_event_ids': [source['id']],
                'source_representations': [self.representation], 'scope': self.scope,
                'reason': 'User-authorized software QA only: exact fixture, obligation, representation and bounded mechanism.',
                'reopen_conditions': ['A changed fixture, mechanism or scope requires a new explicit review.']}]}
        write_json(self.out / 'operator-blueprint.json', blueprint)
        result = ResearchStore(self.db).frontier.import_history(blueprint, 'User-authorized isolated positive lifecycle QA')
        write_json(self.out / 'operator-import.json', result)
        self.ids['obligation'] = result['obligation_ids']['qa']
        self.frontier_version = 1

    async def positive(self, minimal=False):
        name = 'minimal_move' if minimal else 'positive_move'
        observable = 'sha256' if minimal else 'byte_length'
        expected = self.fixture_hash if minimal else len(self.fixture)
        proposal = self.proposal(observable, expected, optional=not minimal)
        record = await self.propose(name, proposal)
        self.check(name + ':record_does_not_activate', not record['execution_permission']['allowed'] and record['status']=='AUDITED')
        audited = await self.audit(name, record['id'])
        self.check(name + ':audit_does_not_activate', not audited['execution_permission']['allowed'] and audited['status']=='AUDITED')
        repeated_audit = await self.audit(name, record['id'])
        self.check(name + ':audit_key_idempotent', repeated_audit['idempotent'] and len(repeated_audit['audits'])==len(audited['audits']))
        activated = await self.transition(name + ':activate', record['id'], 'activate_experiment')
        self.check(name + ':explicit_activation', activated['execution_permission']['allowed']
                   and activated['execution_permission']['scope']==self.scope
                   and not activated['execution_permission']['proof_allowed']
                   and not activated['execution_permission']['transformation_allowed'])
        done = await self.complete(name, record['id'], observable, expected)
        compact_path = list(dict.fromkeys(item['status'] for item in done['history']))
        self.check(name + ':positive_cycle', compact_path==['PROPOSED','AUDITED','EXPERIMENT_ALLOWED','COMPLETED']
                   and done['proof_status']=='unverified' and not done['execution_permission']['allowed'])
        denied = await self.transition(name + ':reactivate', record['id'], 'activate_experiment', allow_error=True)
        self.check(name + ':terminal_reactivation_blocked', denied is None)
        before = len([row for row in snapshot(self.db)['tables']['research_moves'] if row['project']==self.project])
        replay = await self.propose(name, proposal)
        after = len([row for row in snapshot(self.db)['tables']['research_moves'] if row['project']==self.project])
        self.check(name + ':proposal_key_idempotent', replay['id']==record['id'] and replay['idempotent'] and before==after)
        old_grant = await self.transition(name + ':activate', record['id'], 'activate_experiment')
        self.check(name + ':old_activation_key_does_not_reactivate', old_grant['status']=='COMPLETED' and not old_grant['execution_permission']['allowed'])

    async def revision(self):
        move = await self.propose('revision_move', self.proposal('lf_count', self.fixture.count(b'\n')))
        await self.audit('revision', move['id'])
        allowed = await self.transition('revision:activate', move['id'], 'activate_experiment')
        self.check('revision:initial_permission', allowed['execution_permission']['allowed'])
        updated = await self.call('research_obligation_update', {'project':self.project,
            'obligation_id':self.ids['obligation'], 'expected_version':1,
            'changes':{'status':'TESTING'}})
        self.frontier_version = updated['version']
        stale = await self.history(move['id'])
        self.check('revision:permission_revoked', stale['status']=='REQUIRES_REVIEW' and not stale['execution_permission']['allowed'])
        denied = await self.transition('revision:stale-activate', move['id'], 'activate_experiment', allow_error=True)
        self.check('revision:reaudit_required', denied is None)
        stale_key = await self.transition('revision:activate', move['id'], 'activate_experiment')
        self.check('revision:old_key_cannot_restore_permission', not stale_key['execution_permission']['allowed'])
        audited = await self.audit('revision-new-version', move['id'])
        self.check('revision:fresh_audit_not_activation', audited['status']=='AUDITED' and not audited['execution_permission']['allowed'])
        fresh = await self.transition('revision:new-activate', move['id'], 'activate_experiment')
        self.check('revision:explicit_new_activation', fresh['execution_permission']['allowed']
                   and fresh['execution_permission']['frontier_versions'][str(self.ids['obligation'])]==self.frontier_version)
        await self.complete('revision', move['id'], 'lf_count', self.fixture.count(b'\n'))

    async def completion_controls(self):
        move = await self.propose('completion_control', self.proposal('byte_sum', sum(self.fixture)))
        await self.audit('completion-control', move['id'])
        await self.transition('completion-control:activate', move['id'], 'activate_experiment')
        no_reason = await self.transition('completion-control:no-reason', move['id'], 'complete',
            allow_error=True, evidence_refs=['event:' + str(self.ids['source_event'])],
            result={'outcome':'ERROR','summary':'Reason is deliberately missing.'})
        self.check('completion:reason_required', no_reason is None)
        no_ref = await self.transition('completion-control:no-reference', move['id'], 'complete',
            allow_error=True, reason='Negative control without an evidence reference.',
            result={'outcome':'ERROR','summary':'Reference is deliberately missing.'})
        self.check('completion:evidence_reference_required', no_ref is None)
        no_result = await self.transition('completion-control:no-result', move['id'], 'complete',
            allow_error=True, reason='QA negative control: no outcome measurement/result was supplied.',
            evidence_refs=['event:' + str(self.ids['source_event'])])
        self.check('completion:actual_result_required', no_result is None,
            'Only the original source event was referenced; no byte_sum result event or outcome field was supplied. '
            + ('Server rejected completion.' if no_result is None else 'Server nevertheless returned '+no_result['status']+'.'))
        await self.completion_boundaries(move['id'])
        if no_result is None:
            await self.complete('completion_control',move['id'],'byte_sum',sum(self.fixture),outcome='INCONCLUSIVE')

    async def contradictory(self):
        counter = await self.event('contradictory_evidence', {'software_qa_only':True,
            'fixture_sha256':self.fixture_hash, 'observable':'byte_length',
            'value_a':len(self.fixture), 'value_b':len(self.fixture)+1,
            'contradiction':True, 'control':'Deliberately conflicting readings for the same immutable fixture; not two true results.'},
            kind='counterexample', status='counterexample')
        request = self.proposal('byte_length', str(len(self.fixture))+' AND '+str(len(self.fixture)+1))
        request['parent_event_ids'].append(counter)
        request['evidence_refs'].append('event:'+str(counter))
        request['proposed_operation']['premises'].extend([
            'The same immutable fixture has byte_length='+str(len(self.fixture)),
            'The same immutable fixture has byte_length='+str(len(self.fixture)+1)])
        record = await self.propose('contradictory_move', request)
        audited = await self.audit('contradictory', record['id'])
        activation = await self.transition('contradictory:activate', record['id'], 'activate_experiment', allow_error=True)
        safe = audited['status'] in {'REQUIRES_REVIEW','REJECTED'} and activation is None
        self.check('contradictory_evidence:requires_review_without_permission', safe,
                   'Audit status='+audited['status']+'; activation '+('rejected' if activation is None else 'allowed')+'.')
        if activation is not None and activation['execution_permission']['allowed']:
            withdrawn = await self.transition('contradictory:withdraw', record['id'], 'abandon',
                reason='Withdraw negative QA control: contradictory evidence was not adjudicated; no experiment executed.')
            self.check('contradictory_evidence:unsafe_qa_grant_withdrawn', not withdrawn['execution_permission']['allowed'])
        else:
            self.check('contradictory_evidence:unsafe_qa_grant_withdrawn',activation is None,
                       'No unsafe grant was issued; nothing needed withdrawal.')

    async def scope_controls(self):
        move = self.proposal('qa_scope_control', 'no permission')
        operation = dict(move['proposed_operation'], mechanism='qa_unapproved_mechanism')
        params = {k:v for k,v in move.items() if k not in {'active_frontier_version','scope','proposal'}}
        params['proposed_operation'] = operation
        result = await self.call('audit_research_shift', {'project':self.project, **params})
        self.check('scope:other_mechanism_not_allowed', result['verdict']!='EXPERIMENT_ALLOWED')
        params['proposed_operation'] = move['proposed_operation']
        params['source_representation']=params['target_representation']='qa_foreign_fixture'
        result = await self.call('audit_research_shift', {'project':self.project, **params})
        self.check('scope:other_source_not_allowed', result['verdict']!='EXPERIMENT_ALLOWED')
        expanded = dict(move, scope=self.scope+' Expanded scope is a negative QA control.')
        result = await self.propose('scope_control', expanded)
        self.check('scope:other_scope_not_allowed', not result['execution_permission']['allowed']
                   and 'EXPERIMENT_SCOPE_REQUIRES_REVIEW' in result['audit']['warnings'])
        foreign = await self.call('audit_research_shift', {'project':self.project+'_OTHER', **params}, allow_error=True)
        self.check('scope:cross_project_sources_rejected', foreign is None)

    async def run(self, token):
        async with httpx.AsyncClient(headers={'Authorization':'Bearer '+token}, timeout=35,
                event_hooks={'request':[self.request_hook], 'response':[self.response_hook]}) as http:
            async with streamable_http_client(self.endpoint, http_client=http) as (read,write,_):
                async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=40),
                    client_info=types.Implementation(name='LivingMath positive acceptance QA',version='0.4.2')) as session:
                    self.session=session
                    init=await session.initialize()
                    catalog=await session.list_tools()
                    write_json(self.out/'tools-list.json',catalog.model_dump(mode='json'))
                    self.installed_version=init.serverInfo.version
                    self.check('transport:real_v041_mcp',init.serverInfo.version=='0.4.2' and len(catalog.tools)==18,
                               'Original invariant identifier retained; current required version is 0.4.2.')
                    self.check('transport:installed_v042',init.serverInfo.version=='0.4.2')
                    try:
                        await self.event('source_event',{'fixture_sha256':self.fixture_hash,
                            'bytes_hex':self.fixture.hex(),'artifact':'artifact:fixture.bin',
                            'software_qa_only':True,'purpose':'Immutable bounded measurement source; no completion outcome.'},
                            kind='qa_source',status='observation',parent=False)
                        self.seed()
                        frontier=await self.call('research_frontier',{'project':self.project,'include_closed':True})
                        self.ids['constraint']=frontier['constraints'][0]['id']
                        self.check('setup:single_scoped_constraint',len(frontier['constraints'])==1
                            and frontier['constraints'][0]['mechanisms']==['qa_bounded_measurement']
                            and frontier['constraints'][0]['obligation_id']==self.ids['obligation'])
                        await self.positive()
                        await self.positive(minimal=True)
                        await self.revision()
                        await self.completion_controls()
                        await self.contradictory()
                        await self.scope_controls()
                        await self.additional_outcomes()
                        await self.adverse_boundaries()
                        await self.legacy_replay()
                        forbidden=await self.call('record_result',{'project':self.project,'kind':'qa_control',
                            'focus':'Forbidden verification control','result':'Must not be stored as verified','status':'verified'},allow_error=True)
                        self.check('verification:model_cannot_assign_verified',forbidden is None)
                    finally:
                        final=[]
                        for move_id in self.moves:
                            current=await self.history(move_id)
                            if current['execution_permission']['allowed']:
                                current=await self.transition('cleanup:'+str(move_id),move_id,'abandon',
                                    reason='QA cleanup: no active test permission should remain after the acceptance run.')
                            final.append(current)
                        write_json(self.out/'final-moves.json',final)
                        write_json(self.out/'objects.json',{'project':self.project,**self.ids})
                    self.health=await self.call('service_health',{})
                    self.check('verification:no_qa_move_verified',all(item['proof_status']=='unverified' for item in final))
                    self.check('cleanup:no_active_qa_permissions',all(not item['execution_permission']['allowed'] for item in final))


def oauth(config, runner):
    registration=None
    origin=runner.origin
    callback='https://chatgpt.com/connector/oauth/livingmath-positive-qa'
    try:
        with httpx.Client(base_url=origin,timeout=35,follow_redirects=False) as http:
            response=http.post('/register',json={'client_name':'LivingMath positive lifecycle QA',
                'redirect_uris':[callback],'grant_types':['authorization_code','refresh_token'],
                'response_types':['code'],'token_endpoint_auth_method':'client_secret_post','scope':'research'})
            response.raise_for_status()
            registration=response.json()
            verifier=secrets.token_urlsafe(48)
            challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            state=secrets.token_urlsafe(32)
            response=http.get('/authorize',params={'client_id':registration['client_id'],'redirect_uri':callback,
                'response_type':'code','code_challenge':challenge,'code_challenge_method':'S256',
                'scope':'research','state':state,'resource':runner.endpoint})
            assert response.status_code in (302,303,307)
            login=response.headers['location']
            assert login.startswith(origin+'/login?')
            assert http.get(login).status_code==200
            request_id=parse_qs(urlparse(login).query)['request'][0]
            response=http.post('/login',data={'request':request_id,
                'password':Path(config['LIVE_MATH_PASSWORD_FILE']).expanduser().read_text().strip()},headers={'Origin':origin})
            assert response.status_code==303
            query=parse_qs(urlparse(response.headers['location']).query)
            assert query['state']==[state]
            response=http.post('/token',data={'grant_type':'authorization_code','client_id':registration['client_id'],
                'client_secret':registration['client_secret'],'code':query['code'][0], 'code_verifier':verifier,
                'redirect_uri':callback,'resource':runner.endpoint})
            response.raise_for_status()
            asyncio.run(runner.run(response.json()['access_token']))
    finally:
        if registration:
            oauth_db=Path(config['LIVE_MATH_DATA_DIR']).expanduser()/'oauth.sqlite3'
            with closing(sqlite3.connect(oauth_db)) as connection,connection:
                keys=[(key,) for key,body in connection.execute('SELECT key,body FROM auth_records')
                      if json.loads(body).get('client_id')==registration['client_id']]
                connection.executemany('DELETE FROM auth_records WHERE key=?',keys)


def final_integrity(runner,before):
    after=snapshot(runner.db)
    unchanged={}
    for name,rows in before['tables'].items():
        actual=after['tables'][name]
        unchanged[name]=actual[:len(rows)]==rows
    runner.check('preservation:all_original_rows_unchanged',all(unchanged.values()),json.dumps(unchanged,sort_keys=True))
    runner.check('preservation:original_audit_prefix_unchanged',unchanged['operations'])
    prev='GENESIS'
    chain_ok=True
    for entry in after['tables']['operations']:
        expected=fingerprint_hash({'time':entry['occurred_at'],'action':entry['action'],
            'details':json.loads(entry['details_json']),'previous':prev})
        if entry['previous_hash']!=prev or entry['entry_hash']!=expected:chain_ok=False
        prev=entry['entry_hash']
    runner.check('integrity:complete_hash_chain',chain_ok)
    with closing(sqlite3.connect(runner.db)) as connection:
        integrity=connection.execute('PRAGMA integrity_check').fetchone()[0]
        foreign_keys=connection.execute('PRAGMA foreign_key_check').fetchall()
        runner.check('integrity:sqlite',integrity=='ok' and not foreign_keys)
        move_id=runner.moves[0]
        probes=[]
        for table,column,where,value in [
            ('research_moves','project','id',move_id),
            ('research_move_audits','move_id','move_id',move_id),
            ('research_move_status_history','move_id','move_id',move_id),
            ('research_move_bindings','move_id','move_id',move_id),
            ('research_move_request_keys','project','project',runner.project),
            ('adverse_evidence_reviews','event_id','project',runner.project),
            ('research_obligation_versions','obligation_id','obligation_id',runner.ids['obligation'])]:
            for action,sql in [('UPDATE','UPDATE '+table+' SET '+column+'='+column+' WHERE '+where+'=?'),
                               ('DELETE','DELETE FROM '+table+' WHERE '+where+'=?')]:
                connection.execute('SAVEPOINT qa_append_only')
                try:
                    connection.execute(sql,(value,))
                    probes.append({'table':table,'action':action,'blocked':False})
                except sqlite3.IntegrityError as error:
                    probes.append({'table':table,'action':action,'blocked':True,'error':str(error)})
                finally:
                    connection.execute('ROLLBACK TO qa_append_only')
                    connection.execute('RELEASE qa_append_only')
        runner.check('integrity:append_only_guards',all(item['blocked'] for item in probes))
    qa_events=[row for row in after['tables']['events'] if row['project']==runner.project]
    runner.check('verification:no_qa_event_verified',all(row['status']!='verified' for row in qa_events))
    runner.check('preservation:database_not_replaced',before['inode']==after['inode'])
    write_json(runner.out/'integrity.json',{'all_original_tables':unchanged,'append_only_probes':probes,
        'old_event_count':len(before['tables']['events']),'new_event_count':len(after['tables']['events']),
        'old_operation_count':len(before['tables']['operations']),'new_operation_count':len(after['tables']['operations']),
        'last_hash':prev,'integrity':integrity,'foreign_key_check':foreign_keys})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,help='Fresh private QA directory; a Backup API snapshot is created before writes')
    args=parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    out=Path(args.out).expanduser().resolve()
    if (out/'calls.json').exists():raise SystemExit('Refusing to replay a finished or interrupted QA run; inspect its traces first.')
    config={}
    config_path=Path(os.environ.get('LIVE_MATH_QA_CONFIG',str(Path.home()/'.config/livingmath/server.env')))
    for line in config_path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            key,value=line.split('=',1)
            config[key]=shlex.split(value)[0]
    db=(Path(config['LIVE_MATH_DATA_DIR']).expanduser()/'research.sqlite3').resolve(strict=True)
    out.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not (out/'before.json').exists():
        backup_path=out/'research-before.sqlite3'
        if backup_path.exists():raise SystemExit('Existing backup without manifest; inspect it rather than overwriting it.')
        with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as connection, closing(sqlite3.connect(backup_path)) as backup:
            if connection.execute('PRAGMA user_version').fetchone()[0]!=5:
                raise SystemExit('Expected an already migrated schema-5 database; QA does not migrate production.')
            connection.backup(backup)
        backup_path.chmod(0o600)
        baseline=snapshot(backup_path)
        baseline['inode']=db.stat().st_ino
        write_json(out/'before.json',baseline)
    before=json.loads((out/'before.json').read_text())
    runner=Acceptance(out,db,config['LIVE_MATH_PUBLIC_URL'].rstrip('/'))
    measured={'fixture_sha256':runner.fixture_hash,'byte_length':len(runner.fixture),
        'sha256':runner.fixture_hash,'lf_count':runner.fixture.count(b'\n'),'byte_sum':sum(runner.fixture),
        'software_qa_only':True,'mathematical_results_verified':False}
    write_json(out/'measurements.json',measured)
    completed=False
    try:
        oauth(config,runner)
        completed=True
    finally:
        if not completed:
            runner.check('harness:run_completed',False,'The live run was interrupted; partial checks cannot establish acceptance.')
        if runner.moves:final_integrity(runner,before)
        summary={'project':runner.project,'endpoint':runner.endpoint,'objects':runner.ids,
            'invariants':runner.checks,'result':'FAIL' if any(c['result']=='FAIL' for c in runner.checks) else 'PASS',
            'pass_count':sum(c['result']=='PASS' for c in runner.checks),'fail_count':sum(c['result']=='FAIL' for c in runner.checks),
            'mcp_call_count':len(runner.calls),'tested_server_version':getattr(runner,'installed_version',None),'server_code_modified':False,
            'mathematical_results_verified':False}
        write_json(out/'result.json',summary)
        print(json.dumps(summary,ensure_ascii=False,indent=2))
    if summary['result']=='FAIL':raise SystemExit(1)


if __name__=='__main__':main()

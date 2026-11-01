"""018 real TLS/OAuth replay of frozen017 policy on isolated copies only."""
import argparse
import asyncio
from contextlib import asynccontextmanager
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import sqlite3
import sys
import time
import traceback

import httpx
from engine017_qa import Acceptance017, append, backup, SOURCE
from engine017_integrity import verify_private, cleanup_fault_copies
from deploy018_storage import migrate, inventory, restore
from deploy018_authority import install, reconcile
from deploy018_transport import serving, client
from qa_positive_acceptance import snapshot, write_json
from normalizer import canonical
from research_store import ResearchStore


def owner_corrupt(c, table, mutation):
    """Explicit trusted-DDL fault injection, exclusively on disposable copies."""
    names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,))]
    for name in names:
        c.execute('DROP TRIGGER "' + name + '"')
    mutation(c)


class Acceptance018(Acceptance017):
    def __init__(self, base, output):
        super().__init__(base, output)
        # The accepted017 controller still uses its own isolated typed DB.
        os.link(self.legacy, self.workspace / 'research.sqlite3')
        self.migrations = {'legacy': migrate(self.legacy), 'engine': migrate(self.db)}
        install(self.db)
        self.negative_attestations_done = False
        self.security = []
        self.port = None

    def owner(self, action, payload):
        result, code = self.command('deploy018_authority.py', payload, action=action)
        append(self.out / 'cycle-ledger.jsonl', {'authority': 'local018 owner', 'action': action, 'request': payload, 'response': result})
        return result, code

    def execute(self, world, move_id, database=None, unreadable=False):
        payload = {'project': world['project'], 'move_id': move_id,
            'environment_file': '/denied-before-environment-open' if unreadable else world['environment'],
            'private_key_file': '/denied-before-key-open' if unreadable else world['private_key_file']}
        result, code = self.command('deploy018_authority.py', payload, database=database, action='execute')
        append(self.out / 'cycle-ledger.jsonl', {'authority': 'local018 pinned executor',
            'request': {'project': world['project'], 'move_id': move_id}, 'response': result})
        return result, code

    @asynccontextmanager
    async def session(self, enabled=True, database=None):
        self.session_count += 1
        label = 'https-' + str(self.session_count)
        forbidden = [self.base / 'frozen/oracle.py'] + list(self.seals.iterdir())
        # Owner-only supervisor action, outside HTTP/model authority.
        reconcile(database or self.db)
        async with serving(self.workspace, database or self.db, self.out, label, forbidden, enabled, self.port) as (origin, ctx, tokens, process):
            if self.port is None:
                self.port = int(origin.rsplit(':', 1)[1])
            async with client(origin, ctx, tokens['access_token'], self.out / 'http-wire.jsonl') as connection:
                initialized = (await connection.initialize()).model_dump(mode='json')
                tools = (await connection.list_tools()).model_dump(mode='json')
                append(self.out / 'catalogues.jsonl', {'session': label, 'enabled': enabled, 'origin': origin,
                    'TLS': 'private pinned CA; loopback; NOT public ingress', 'initialize': initialized, 'tools': tools})
                self.check(label + ':capabilities', len(tools['tools']) == (27 if enabled else 24))
                self.check(label + ':no_operator_tool', not {'activate', 'execute', 'commit', 'register_source'} & {t['name'] for t in tools['tools']})
                if enabled and label == 'https-2':
                    await self.auth_controls(origin, ctx, tokens['access_token'])
                    contract, _ = await super().call(connection, 'research_contract', {})
                    self.check('018_versioned_contract', contract['http018']['version'] == '018.1')
                yield connection

    async def auth_controls(self, origin, ctx, token):
        auth_db = self.workspace / 'oauth.sqlite3'
        from http_auth import OwnerOAuthProvider
        key = OwnerOAuthProvider._key('access', token)
        async with httpx.AsyncClient(verify=ctx, timeout=5) as http:
            async def probe(label, bearer=None):
                headers = {'Accept': 'application/json, text/event-stream'}
                if bearer:
                    headers['Authorization'] = 'Bearer ' + bearer
                r = await http.post(origin + '/mcp', headers=headers,
                    json={'jsonrpc': '2.0', 'id': 991, 'method': 'tools/list'})
                self.security.append({'control': label, 'http_status': r.status_code})
                self.check('auth:' + label, r.status_code in (401, 403), r.status_code)
            await probe('unauthenticated')
            await probe('invalid_token', 'LM018-invalid-token')
            with sqlite3.connect(auth_db) as c:
                row = c.execute('SELECT body,expires FROM auth_records WHERE key=?', (key,)).fetchone()
                c.execute('UPDATE auth_records SET expires=0 WHERE key=?', (key,))
            await probe('expired', token)
            with sqlite3.connect(auth_db) as c:
                body = json.loads(row[0]); body['scopes'] = ['different_scope']
                c.execute('UPDATE auth_records SET expires=?,body=? WHERE key=?', (row[1], canonical(body), key))
            await probe('wrong_scope', token)
            with sqlite3.connect(auth_db) as c:
                c.execute('UPDATE auth_records SET body=? WHERE key=?', (row[0], key))
                # Separate genuine access token is obtained/revoked for this test.
            from deploy018_transport import oauth
            separate = await asyncio.to_thread(oauth, origin, ctx, self.workspace / 'tls/owner-password')
            r = await http.post(origin + '/revoke', data={'token': separate['access_token'],
                'client_id': separate['client_id'], 'client_secret': separate['client_secret']})
            self.check('auth:revocation_protocol', r.status_code == 200, r.status_code)
            await probe('revoked', separate['access_token'])
            # Actual body and interrupted-body controls, no JSON-RPC dispatch.
            before = snapshot(self.db)
            r = await http.post(origin + '/mcp', headers={'Authorization': 'Bearer ' + token}, content=b'x' * 262145)
            self.check('http:payload_limit', r.status_code == 413 and snapshot(self.db) == before, r.status_code)
        write_json(self.out / 'security-controls.json', self.security)

    async def call(self, connection, name, arguments, allow_error=False):
        result, error = await super().call(connection, name, arguments, allow_error)
        if name == 'research_cycle_validate' and result.get('status') == 'VALID_BOUND_MEASUREMENT' and not self.negative_attestations_done:
            self.negative_attestations_done = True
            await self.attestation_controls(arguments)
        return result, error

    async def attestation_controls(self, args):
        folder = self.workspace / 'attestation-faults'
        folder.mkdir()
        for label in ('nonce', 'key_id', 'project', 'signature', 'expiry', 'source_signature', 'artifact_hash'):
            query_args = dict(args)
            db = folder / (label + '.sqlite3')
            backup(self.db, db)
            with sqlite3.connect(db) as c:
                if label in ('source_signature', 'artifact_hash'):
                    from normalizer import digest
                    row = c.execute('SELECT payload_json FROM typed011_executions WHERE move_id=?', (args['move_id'],)).fetchone()
                    local = json.loads(row[0])
                    artifact = json.loads(Path(local['artifact_path']).read_text())
                    artifact['signature'] = '00' * 64
                    path = Path(local['artifact_path']).with_name('fault018-' + label + '.json')
                    path.write_text(canonical(artifact))
                    local['artifact_path'] = str(path)
                    if label == 'source_signature':
                        local['artifact_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                        event = json.loads(c.execute('SELECT content FROM events WHERE id=?', (args['event_id'],)).fetchone()[0])
                        event['measurement_binding']['artifact_sha256'] = local['artifact_sha256']
                        local['envelope_sha256'] = digest(event['measurement_binding'])
                        # Append a corrupt carrier rather than altering original
                        # evidence/hash-chain. Only disposable execution linkage
                        # is changed by the explicitly trusted schema owner.
                        c.commit()
                        created = ResearchStore(db).record(args['project'], 'experiment', '018 corrupt signed carrier',
                            canonical(event), 'experiment', request_key='018:fault-source-signature')
                        query_args['event_id'] = created['id']
                    owner_corrupt(c, 'typed011_executions', lambda c: c.execute('UPDATE typed011_executions SET event_id=?,payload_json=? WHERE move_id=?',
                        (query_args['event_id'], canonical(local), args['move_id'])))
                elif label == 'expiry':
                    owner_corrupt(c, 'deploy018_leases', lambda c: c.execute('UPDATE deploy018_leases SET expires=0 WHERE move_id=?', (args['move_id'],)))
                else:
                    payload = json.loads(c.execute('SELECT payload_json FROM deploy018_attestations WHERE move_id=?', (args['move_id'],)).fetchone()[0])
                    if label == 'signature':
                        payload['signature'] = '00' * 64
                    else:
                        payload['body']['lease'][label] = 'tampered'
                    owner_corrupt(c, 'deploy018_attestations', lambda c: c.execute('UPDATE deploy018_attestations SET payload_json=? WHERE move_id=?', (canonical(payload), args['move_id'])))
            # Do not reconcile here: it would mask the precise signature/nonce
            # failure by first revoking the deliberately active disposable copy.
            label_id = 'signed-control-' + label
            forbidden = [self.base / 'frozen/oracle.py'] + list(self.seals.iterdir())
            async with serving(self.workspace, db, self.out, label_id, forbidden) as (origin, ctx, tokens, process):
                async with client(origin, ctx, tokens['access_token'], self.out / 'http-wire.jsonl') as connection:
                    await connection.initialize()
                    await connection.list_tools()
                    before = snapshot(db)
                    rejected, _ = await super().call(connection, 'research_cycle_validate', query_args)
                    expected = {'source_signature': 'EXECUTOR_SIGNATURE_INVALID', 'artifact_hash': 'ARTIFACT_DIGEST_MISMATCH',
                        'signature': '018_ATTESTATION_SIGNATURE_INVALID', 'expiry': '018_LEASE_EXPIRED_REAUDIT_REQUIRED'}.get(label, '018_NONCE_OR_MEASUREMENT_REBIND')
                    self.check('signed_http:' + label, rejected['status'] == 'REJECTED' and expected in rejected['reason'] and snapshot(db) == before, rejected)
            reconcile(db, 'End of deliberate018 signed-corruption control')

    def active_controls(self, world, pc):
        folder = self.private / 'active-controls'
        folder.mkdir(exist_ok=True)
        for label, field, value in [('observer', 'observer', {'projection': 'primary', 'mod': 2}),
            ('source_hash', 'native_definition_sha256', '0' * 64), ('test_id', 'test_id', 'foreign-test'),
            ('ordered_suffix', 'suffix', ['invalid-action'])]:
            db = folder / (label + '.sqlite3')
            backup(self.db, db)
            with sqlite3.connect(db) as c:
                row = c.execute('SELECT p.id,p.payload_json FROM typed011_precommits p JOIN typed011_moves m ON m.precommit_id=p.id WHERE m.move_id=?', (pc['move_id'],)).fetchone()
                payload = json.loads(row[1]); payload[field] = value
                from normalizer import digest
                owner_corrupt(c, 'typed011_precommits', lambda c: c.execute('UPDATE typed011_precommits SET payload_json=?,digest=? WHERE id=?', (canonical(payload), digest(payload), row[0])))
            value, code = self.execute(world, pc['move_id'], db, unreadable=True)
            self.check('active:' + label, code != 0 and 'denied-before' not in value.get('error', ''), value)
            reconcile(db, 'End of018 active-control copy')

    async def legacy_cycle(self, connection):
        # Explicit reviewed018 policy change, not silently passing old grants.
        before = snapshot(self.legacy)
        for action in ('activate_experiment', 'complete'):
            denied, error = await self.call(connection, 'transition_research_move', {
                'project': 'LM_QA_018_CANARY', 'move_id': 1, 'action': action,
                'reason': '018 model authority negative control', 'request_key': '018:denied:' + action}, True)
            self.check('legacy_model:' + action, error and snapshot(self.legacy) == before, denied)

    async def context_fault_controls(self):
        folder = self.workspace / 'context-faults'
        folder.mkdir()
        world = self.worlds['A0']
        row = next(r for r in reversed(self.calls) if r['tool'] == 'research_cycle_next' and
            r['arguments']['query']['project'] == world['project'] and not r['response'].get('isError'))
        current = row['response'].get('structuredContent') or json.loads(row['response']['content'][0]['text'])
        for label in ('journal_conflict', 'uninspected_source', 'incomplete_source'):
            db = folder / (label + '.sqlite3')
            backup(self.db, db)
            with sqlite3.connect(db) as c:
                if label == 'journal_conflict':
                    receipt_id = c.execute('SELECT max(id) FROM typed011_receipts WHERE project=?', (world['project'],)).fetchone()[0]
                    c.execute('INSERT INTO typed011_journal(project,scope,source_family_id,claim_fingerprint,raw_sha256,receipt_id,payload_json) VALUES (?,?,?,?,?,?,?)',
                        (world['project'], world['manifest']['scope'], current['source_family_id'], current['claim_fingerprint'], '0' * 64, receipt_id,
                         canonical({'fault': 'Explicit owner-controlled contradictory raw distinction'})))
                elif label == 'uninspected_source':
                    manifest = json.loads(c.execute('SELECT payload_json FROM engine017_sources WHERE project=?', (world['project'],)).fetchone()[0])
                    manifest['inspection_status'] = 'DECLARED_UNINSPECTED'
                    owner_corrupt(c, 'engine017_sources', lambda c: c.execute('UPDATE engine017_sources SET payload_json=? WHERE project=?', (canonical(manifest), world['project'])))
                else:
                    event = json.loads(c.execute('SELECT content FROM events WHERE id=?', (world['root_id'],)).fetchone()[0])
                    event.pop('source_spec')
                    owner_corrupt(c, 'events', lambda c: c.execute('UPDATE events SET content=? WHERE id=?', (canonical(event), world['root_id'])))
            async with self.session(True, db) as connection:
                value, _ = await self.call(connection, 'research_cycle_next', {'query': {'project': world['project']}})
                expected = 'REQUIRES_REVIEW' if label == 'journal_conflict' else 'INSUFFICIENT_CONTEXT'
                self.check('context:' + label, value['status'] == expected and not value['execution_permission']['allowed'], value)


def prepare(base: Path, source: Path | None = None) -> None:
    """Fresh replay may use an EMPTY canonical DB; historical86 is separate."""
    base.mkdir(parents=True, mode=0o700, exist_ok=True)
    if not (base / 'canonical.sqlite3').exists():
        ResearchStore(base / 'canonical.sqlite3')
    frozen = base / 'frozen'
    frozen.mkdir(exist_ok=False)
    origin = source or Path(Path('/tmp/lm017_path').read_text().strip()) / 'frozen'
    for name in ('pre-registration.json', 'seal.json', 'oracle.py'):
        shutil.copy2(origin / name, frozen / name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frozen', type=Path)
    args = parser.parse_args()
    if not (args.base / 'frozen').exists():
        prepare(args.base, args.frozen)
    runner = Acceptance018(args.base, args.output)
    sources = runner.out / 'sources018'
    sources.mkdir()
    for p in SOURCE.glob('*018*.py'):
        shutil.copy2(p, sources / p.name)
    shutil.copytree(SOURCE / 'migrations', sources / 'migrations')
    write_json(runner.out / '018-implementation-lock.json', {str(p.relative_to(sources)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources.rglob('*') if p.is_file()})
    write_json(args.base / 'current.json', {'output': str(runner.out), 'private': str(runner.private), 'database': str(runner.db), 'legacy': str(runner.legacy)})
    try:
        counts = asyncio.run(runner.run())
        state = verify_private(args.base / 'canonical.sqlite3', runner.db)
        runner.check('original_prefix', all(state['all_original_table_prefixes'].values()))
        runner.check('final_integrity', state['chain']['hash_chain_ok'] and state['chain']['sqlite_integrity'] == 'ok' and not state['chain']['foreign_key_errors'])
        runner.check('no_final_grants_or_verified', not state['own_active_permissions'] and not state['new_verified_events'])
        write_json(runner.out / 'integrity.json', state)
        status = 'PASS_PRIVATE_HTTPS_STAGING'
    except Exception as error:
        status = 'STOP_WITH_RCA'
        counts = dict(Counter(r['receipt']['outcome'] for r in runner.receipts))
        write_json(runner.out / 'exception.json', {'error': str(error), 'traceback': traceback.format_exc()})
    write_json(runner.out / 'result.json', {'status': status, 'deployment': 'NOT_PERFORMED', 'MCP_tool_calls': len(runner.calls),
        'main_HTTP_processes': runner.session_count, 'complete_cycles': counts, 'checks': len(runner.checks), 'proof_status': 'unverified'})
    write_json(runner.out / 'costs.json', {'workers': runner.costs, 'driver_wall_ns': time.perf_counter_ns() - runner.started,
        'driver_CPU_ns': time.process_time_ns() - runner.cpu, 'external_inference': 'NOT_USED'})
    print(canonical({'status': status, 'output': str(runner.out), 'cycles': counts, 'MCP_calls': len(runner.calls)}))
    if status == 'STOP_WITH_RCA':
        raise SystemExit(1)


if __name__ == '__main__':
    main()

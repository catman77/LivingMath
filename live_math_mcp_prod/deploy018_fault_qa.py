"""Bounded018 SIGKILL, real HTTPS load/cancellation and rollback rehearsal."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import resource

import httpx
from deploy018_transport import serving, client
from deploy018_storage import migrate, restore, inventory
from deploy018_authority import install, reconcile
from engine017_fixtures import seed
from engine017_store import install as install017
from typed_cycle011_store import install as install011
from research_store import ResearchStore
from qa_positive_acceptance import snapshot, write_json
from normalizer import canonical

SOURCE = Path(__file__).resolve().parent


def request_for(world, pc, measured):
    env = measured['envelope']
    return {'project': world['project'], 'move_id': pc['move_id'], 'event_id': measured['event_id'], 'request_key': '018-fault-commit',
        **{k: env[k] for k in ('outcome', 'observed', 'summary', 'reason', 'proof_status')}}


class Faults:
    def __init__(self, base: Path, out: Path):
        self.base, self.out = base, out
        out.mkdir(parents=True, exist_ok=False)
        self.private = base / ('faults-' + out.name)
        self.private.mkdir(mode=0o700)
        self.policy = json.loads((base / 'frozen/pre-registration.json').read_text())
        self.checks, self.calls = [], 0
        self.started, self.cpu = time.perf_counter_ns(), time.process_time_ns()
        self.children = resource.getrusage(resource.RUSAGE_CHILDREN)

    def check(self, label, ok, detail=None):
        self.checks.append({'control': label, 'result': 'PASS' if ok else 'FAIL', 'detail': detail})
        write_json(self.out / 'fault-matrix.json', self.checks)
        if not ok:
            raise AssertionError(label)

    def setup(self, label):
        directory = self.private / label
        workspace, seals = directory / 'workspace', directory / 'seals'
        workspace.mkdir(parents=True, mode=0o700)
        seals.mkdir(mode=0o700)
        legacy, db = workspace / 'research.sqlite3', workspace / 'engine.sqlite3'
        ResearchStore(legacy)
        ResearchStore(db)
        install011(db, legacy)
        install017(db)
        migrate(legacy)
        migrate(db)
        install(db)
        world = seed(db, workspace, seals, self.policy['families'][0], self.policy['cases'][0], 'FAULT018-' + label)
        return workspace, seals, db, world

    async def call(self, connection, name, args, allow_error=False):
        self.calls += 1
        reply = await connection.call_tool(name, args)
        text = ''.join(c.text for c in reply.content if c.type == 'text')
        try:
            value = reply.structuredContent or json.loads(text)
        except ValueError:
            value = {'error': text}
        self.check(name + ':transport:' + str(self.calls), allow_error or not reply.isError, value if reply.isError else None)
        return value

    def command(self, db, action, payload, point=None):
        env = {**os.environ}
        env.pop('LM018_FAULT', None)
        if point:
            env['LM018_FAULT'] = point
        p = subprocess.run([sys.executable, str(SOURCE / 'deploy018_authority.py'), '--db', str(db), action],
            input=canonical(payload), text=True, capture_output=True, env=env, timeout=15)
        value = json.loads(p.stdout) if p.stdout.strip() else None
        # No environment/key path or credentials in published owner request.
        with (self.out / 'owner-faults.jsonl').open('a') as stream:
            stream.write(canonical({'action': action, 'move_id': payload.get('move_id'), 'fault': point,
                'exit_code': p.returncode, 'result': value}) + '\n')
        return p.returncode, value

    async def authority_kills(self):
        for point in ('audit_transaction', 'activation_after_grant', 'activation_transaction',
                      'execution_prepared', 'execution_after_event', 'commit_transaction', 'commit_after_commit'):
            workspace, seals, db, world = self.setup(point)
            forbidden = [self.base / 'frozen/oracle.py'] + list(seals.iterdir())
            async with serving(workspace, db, self.out, point, forbidden) as (origin, ctx, tokens, process):
                async with client(origin, ctx, tokens['access_token'], self.out / 'http-wire.jsonl') as connection:
                    await connection.initialize(); await connection.list_tools()
                    pc = await self.call(connection, 'research_cycle_precommit', {'request': {'project': world['project']}, 'request_key': point})
                    payload = {'project': world['project'], 'move_id': pc['move_id'], 'request_key': point}
                    action = 'activate'
                    if point.startswith(('execution', 'commit')):
                        code, result = self.command(db, 'activate', payload)
                        self.check(point + ':activation', code == 0, result)
                        payload = {'project': world['project'], 'move_id': pc['move_id'],
                            'environment_file': world['environment'], 'private_key_file': world['private_key_file']}
                        action = 'execute'
                    if point.startswith('commit'):
                        code, result = self.command(db, 'execute', payload)
                        self.check(point + ':measurement', code == 0, result)
                        action, payload = 'commit', request_for(world, pc, result['result'])
                    before = snapshot(db)
                    code, result = self.command(db, action, payload, point)
                    self.check(point + ':SIGKILL', code == -9, code)
                    after = snapshot(db)
                    self.check(point + ':old_rows_preserved', all(after['tables'][t][:len(rows)] == rows for t, rows in before['tables'].items()))
                    if point in ('audit_transaction', 'commit_transaction'):
                        self.check(point + ':atomic_rollback', before == after)
                    if point == 'commit_after_commit':
                        code, result = self.command(db, 'commit', payload)
                        self.check(point + ':exactly_once_replay', code == 0 and result['result']['idempotent'])
                    retired = reconcile(db)
                    history = await self.call(connection, 'research_cycle_history', {'project': world['project']})
                    self.check(point + ':no_ghost_grant', all(not m['execution_permission']['allowed'] for m in history['moves']), retired)
                    state = inventory(db)
                    self.check(point + ':chain', state['chain']['hash_chain_ok'] and state['chain']['sqlite_integrity'] == 'ok' and not state['chain']['foreign_key_errors'])

    async def precommit_kills(self):
        for point in ('http_precommit_before', 'http_precommit_after'):
            workspace, seals, db, world = self.setup(point)
            forbidden = [self.base / 'frozen/oracle.py'] + list(seals.iterdir())
            args = {'request': {'project': world['project']}, 'request_key': point}
            try:
                async with serving(workspace, db, self.out, point, forbidden, fault_point=point) as (origin, ctx, tokens, process):
                    async with client(origin, ctx, tokens['access_token'], self.out / 'http-wire.jsonl') as connection:
                        await connection.initialize(); await connection.list_tools()
                        async with asyncio.timeout(5):
                            await connection.call_tool('research_cycle_precommit', args)
            except Exception:
                pass
            self.check(point + ':server_SIGKILL', process.returncode == -9)
            reconcile(db)
            async with serving(workspace, db, self.out, point + '-restart', forbidden) as (origin, ctx, tokens, process):
                async with client(origin, ctx, tokens['access_token'], self.out / 'http-wire.jsonl') as connection:
                    await connection.initialize(); await connection.list_tools()
                    one = await self.call(connection, 'research_cycle_precommit', args)
                    before = snapshot(db)
                    two = await self.call(connection, 'research_cycle_precommit', args)
                    self.check(point + ':replay_once_after_restart', one == two and snapshot(db) == before and not one['execution_permission']['allowed'])

    async def load_controls(self):
        workspace, seals, db, world = self.setup('load')
        forbidden = [self.base / 'frozen/oracle.py'] + list(seals.iterdir())
        async with serving(workspace, db, self.out, 'load', forbidden) as (origin, ctx, tokens, process):
            port = int(origin.rsplit(':', 1)[1])
            before = snapshot(db)
            async def partial():
                read, write = await asyncio.open_connection('127.0.0.1', port, ssl=ctx, server_hostname='localhost')
                write.write(('POST /mcp HTTP/1.1\r\nHost: localhost:' + str(port) + '\r\nContent-Length: 100\r\n\r\nabc').encode())
                await write.drain()
                return read, write
            read, write = await partial()
            response = await asyncio.wait_for(read.read(1024), 4)
            self.check('body_deadline_real_TLS', b'408' in response and b'018_BODY_DEADLINE' in response, response.decode(errors='replace'))
            write.close(); await write.wait_closed()
            read, write = await partial()
            write.close(); await write.wait_closed()
            await asyncio.sleep(0.05)
            self.check('interrupted_body_no_DB_delta', snapshot(db) == before)
            pending = [await partial() for _ in range(8)]
            await asyncio.sleep(0.05)
            async with httpx.AsyncClient(verify=ctx, timeout=5) as http:
                r = await http.post(origin + '/mcp', content=b'{}')
                self.check('concurrency_bound_real_TLS', r.status_code == 429, r.status_code)
            for _, stream in pending:
                stream.close()
            await asyncio.gather(*(stream.wait_closed() for _, stream in pending))
            await asyncio.sleep(0.05)
            self.check('concurrency_rejection_no_DB_delta', snapshot(db) == before)
            limits = Path('/proc/' + str(process.pid) + '/limits').read_text()
            (self.out / 'server-resource-limits.txt').write_text(limits)
            self.check('actual_process_CPU_memory_bounds', '1073741824' in limits and '90' in limits)
            async with client(origin, ctx, tokens['access_token'], self.out / 'http-wire.jsonl') as connection:
                await connection.initialize(); await connection.list_tools()
                args = {'request': {'project': world['project']}, 'request_key': 'cancelled-client'}
                task = asyncio.create_task(connection.call_tool('research_cycle_precommit', args))
                await asyncio.sleep(0)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                one = await self.call(connection, 'research_cycle_precommit', args)
                before = snapshot(db)
                two = await self.call(connection, 'research_cycle_precommit', args)
                self.check('client_cancel_then_exactly_once_key', one == two and snapshot(db) == before and not one['execution_permission']['allowed'])
        async with serving(workspace, db, self.out, 'rate', forbidden, rate=32) as (origin, ctx, tokens, process):
            before = snapshot(db)
            async with httpx.AsyncClient(verify=ctx, timeout=5) as http:
                statuses = [(await http.post(origin + '/mcp', content=b'{}')).status_code for _ in range(40)]
            self.check('rate_limit_real_TLS', 429 in statuses and snapshot(db) == before, statuses)

    async def rollback_and_restore(self, current: dict):
        data, db = Path(current['legacy']).parent, Path(current['database'])
        source = self.private / 'accepted-engine-backup.sqlite3'
        from deploy018_storage import backup
        backup(db, source)
        with sqlite3.connect(db) as c:
            project = c.execute('SELECT project FROM engine017_sources ORDER BY project LIMIT 1').fetchone()[0]
        baseline = snapshot(db)
        forbidden = [self.base / 'frozen/oracle.py']
        old_history = None
        port = None
        for enabled, label in [(True, 'rollout'), (False, 'rollback24'), (True, 'rollforward27')]:
            reconcile(db)
            async with serving(data, db, self.out, label, forbidden, enabled=enabled, port=port) as (origin, ctx, tokens, process):
                port = int(origin.rsplit(':', 1)[1])
                async with client(origin, ctx, tokens['access_token'], self.out / 'http-wire.jsonl') as connection:
                    await connection.initialize()
                    tools = (await connection.list_tools()).tools
                    self.check(label + ':capabilities', len(tools) == (27 if enabled else 24))
                    if enabled:
                        history = await self.call(connection, 'research_cycle_history', {'project': project})
                        if old_history is None:
                            old_history = history
                            value = await self.call(connection, 'record_result', {'project': 'LM_QA_018_CANARY', 'kind': 'qa_source',
                                'focus': 'Private rollout sentinel', 'result': 'Bounded software QA; unverified; no production write',
                                'status': 'observation', 'request_key': '018:private-canary'})
                            self.check('canary_private_namespace', value['project'] == 'LM_QA_018_CANARY')
                        else:
                            self.check('rollback_preserves_history_and_receipts', history == old_history and snapshot(db) == baseline)
                    self.check(label + ':typed_ledger_unchanged', snapshot(db) == baseline)
        # Restore the committed engine snapshot to two new paths and mount both
        # over HTTPS. No config row is rewritten; old canonical binding remains
        # historical provenance, and018 mounts its reviewed isolated adapter.
        restored = []
        for index in ('A', 'B'):
            target = data / 'restores018' / self.out.name / ('committed-restore-' + index + '.sqlite3')
            state = restore(source, target)
            migrate(target)
            async with serving(data, target, self.out, 'restored-' + index, forbidden) as (origin, ctx, tokens, process):
                async with client(origin, ctx, tokens['access_token'], self.out / 'http-wire.jsonl') as connection:
                    await connection.initialize(); await connection.list_tools()
                    history = await self.call(connection, 'research_cycle_history', {'project': project})
                    self.check('restored_' + index + ':exact_committed_history', history == old_history)
            restored.append(state)
        write_json(self.out / 'committed-restore.json', restored)
        # Keep the DB/backup in private state, never inside the capsule.
        restore_target = self.private / 'restore-crash.sqlite3'
        code = 'from pathlib import Path;from deploy018_storage import restore;import sys;restore(Path(sys.argv[1]),Path(sys.argv[2]))'
        source = self.base / 'canonical.sqlite3'
        initial = inventory(source)
        p = subprocess.run([sys.executable, '-c', code, str(source), str(restore_target)], capture_output=True,
            env={**os.environ, 'LM018_FAULT': 'restore_before_publish'}, timeout=15)
        self.check('restore_SIGKILL_no_partial_publish', p.returncode == -9 and not restore_target.exists() and inventory(source) == initial)
        state = restore(source, self.private / 'restore-after-crash.sqlite3')
        self.check('restore_retry_new_path', state['status'] == 'PASS')

    async def run(self, current):
        await self.authority_kills()
        await self.precommit_kills()
        await self.load_controls()
        await self.rollback_and_restore(current)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    runner = Faults(args.base, args.out)
    try:
        asyncio.run(runner.run(json.loads((args.base / 'current.json').read_text())))
        status = 'PASS'
    except Exception as error:
        status = 'STOP_WITH_RCA'
        write_json(args.out / 'exception.json', {'error': str(error), 'traceback': __import__('traceback').format_exc()})
    write_json(args.out / 'result.json', {'status': status, 'checks': len(runner.checks), 'MCP_tool_calls_completed': runner.calls,
        'deployment': 'NOT_PERFORMED', 'scope': 'private HTTP/operator/executor, not production'})
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    write_json(args.out / 'costs.json', {'driver_wall_ns': time.perf_counter_ns() - runner.started,
        'driver_CPU_ns': time.process_time_ns() - runner.cpu,
        'children_CPU_ns': round((usage.ru_utime + usage.ru_stime - runner.children.ru_utime - runner.children.ru_stime) * 1e9),
        'largest_child_peak_RSS_KiB': usage.ru_maxrss, 'external_inference': 'NOT_USED'})
    print(json.dumps({'status': status, 'checks': len(runner.checks), 'output': str(args.out)}))
    if status != 'PASS':
        raise SystemExit(1)

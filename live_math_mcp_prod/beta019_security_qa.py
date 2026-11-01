"""Address-independent network controls against the actual019 beta endpoint."""
import argparse
import asyncio
import json
from pathlib import Path
import time
import httpx
from beta019_admin import initialise
from beta019_seed import seed
from beta019_transport import serving, client
from deploy018_transport import oauth
from qa_positive_acceptance import snapshot, write_json
from research_store import ResearchStore


async def run(root: Path, out: Path):
    out.mkdir(parents=True, exist_ok=False); initialise(root)
    data, db, seals = root / 'state', root / 'state/beta.sqlite3', root / 'seals'
    seals.mkdir(mode=0o700)
    world = seed(db, data, seals, 0, out.name + ':network')
    checks = []
    def check(name, ok, evidence=None):
        checks.append({'control': name, 'result': 'PASS' if ok else 'FAIL', 'evidence': evidence})
        write_json(out / 'security-faults.json', checks)
        if not ok:
            raise AssertionError(name)
    async with serving(data, db, out, 'network', list(seals.iterdir())) as (origin, ctx, tokens, process):
        before = snapshot(db); port = int(origin.rsplit(':', 1)[1])
        async def partial():
            reader, writer = await asyncio.open_connection('127.0.0.1', port, ssl=ctx, server_hostname='localhost')
            writer.write(('POST /mcp HTTP/1.1\r\nHost: localhost:' + str(port) + '\r\nContent-Length: 100\r\n\r\nabc').encode()); await writer.drain()
            return reader, writer
        reader, writer = await partial()
        headers = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 5)
        length = next(int(line.split(b':', 1)[1]) for line in headers.lower().split(b'\r\n') if line.startswith(b'content-length:'))
        response = headers + await asyncio.wait_for(reader.readexactly(length), 5)
        check('actual_TLS_body_timeout408', b'408' in response and b'018_BODY_DEADLINE' in response, response.decode(errors='replace'))
        writer.close(); await writer.wait_closed()
        _, writer = await partial(); writer.close(); await writer.wait_closed(); await asyncio.sleep(.05)
        check('interrupted_body_no_DB_delta', snapshot(db) == before)
        pending = await asyncio.gather(*(partial() for _ in range(8)))
        await asyncio.sleep(.05)
        async with httpx.AsyncClient(verify=ctx, timeout=5) as http:
            r = await http.post(origin + '/mcp', content=b'{}')
            check('actual_TLS_concurrency_limit429', r.status_code == 429 and snapshot(db) == before, r.status_code)
        for _, stream in pending:
            stream.close()
        await asyncio.gather(*(s.wait_closed() for _, s in pending)); await asyncio.sleep(.05)
        other = await asyncio.to_thread(oauth, origin, ctx, data / 'tls/owner-password')
        async with httpx.AsyncClient(verify=ctx, timeout=5) as http:
            r = await http.post(origin + '/token', data={'grant_type': 'refresh_token', 'client_id': tokens['client_id'],
                'client_secret': tokens['client_secret'], 'refresh_token': other['refresh_token'], 'resource': origin + '/mcp'})
            check('refresh_bound_to_correct_client', r.status_code == 400 and r.json()['error'] == 'invalid_grant', r.status_code)
            r = await http.post(origin + '/token', data={'grant_type': 'refresh_token', 'client_id': tokens['client_id'],
                'client_secret': 'deliberately-wrong-secret', 'refresh_token': tokens['refresh_token'], 'resource': origin + '/mcp'})
            check('wrong_client_credentials_denied', r.status_code == 401 and r.json().get('error') == 'unauthorized_client'
                and r.json().get('error_description') == 'Invalid client_secret', {'status': r.status_code, 'error': r.json()})
        async with client(origin, ctx, tokens['access_token'], out / 'http-wire.jsonl') as connection:
            await connection.initialize(); await connection.list_tools()
            args = {'request': {'project': world['project']}, 'request_key': 'cancelled-client'}
            task = asyncio.create_task(connection.call_tool('research_cycle_precommit', args)); await asyncio.sleep(0); task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            reply = await connection.call_tool('research_cycle_precommit', args)
            value = reply.structuredContent or json.loads(reply.content[0].text)
            before = snapshot(db)
            repeat = await connection.call_tool('research_cycle_precommit', args)
            repeated = repeat.structuredContent or json.loads(repeat.content[0].text)
            check('cancel_then_idempotent_proposal_without_grant', not reply.isError and value == repeated and snapshot(db) == before and not value['execution_permission']['allowed'])
            ResearchStore(db).moves.transition(world['project'], value['move_id'], 'abandon', '019:network:cleanup', reason='Local owner retires cancelled QA proposal; no experiment executed.')
        limits = Path('/proc/' + str(process.pid) + '/limits').read_text(); (out / 'process-limits.txt').write_text(limits)
        check('actual_1GiB_90CPU_limits', '1073741824' in limits and '90' in limits)
    async with serving(data, db, out, 'rate', list(seals.iterdir()), rate=32) as (origin, ctx, tokens, process):
        before = snapshot(db)
        async with httpx.AsyncClient(verify=ctx, timeout=5) as http:
            statuses = [(await http.post(origin + '/mcp', content=b'{}')).status_code for _ in range(40)]
        check('actual_TLS_rate_limit429', 429 in statuses and snapshot(db) == before, statuses)
    write_json(out / 'result.json', {'status': 'PASS', 'checks': len(checks), 'scope': 'real019 private HTTPS/OAuth, not mocked', 'deployment': 'NOT_PERFORMED'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--root', type=Path, required=True); parser.add_argument('--out', type=Path, required=True); args = parser.parse_args()
    try:
        asyncio.run(run(args.root, args.out))
    except Exception as error:
        args.out.mkdir(parents=True, exist_ok=True)
        write_json(args.out / 'first-failure.json', {'status': 'STOP_WITH_RCA', 'error': str(error), 'traceback': __import__('traceback').format_exc()})
        raise

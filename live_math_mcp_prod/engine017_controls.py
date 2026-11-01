"""Read-only MCP artifact attacks against restored historical staging snapshots.

Only disposable copies and new tampered artifact files change. No accepted
measurement, receipt or production record is edited.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import resource
import sqlite3
import sys
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from normalizer import canonical, digest
from normalization_regression import Tap
from qa_positive_acceptance import write_json
from engine017_qa import backup

SOURCE = Path(__file__).resolve().parent


def insert_row(c, table, row):
    c.execute('INSERT INTO ' + table + '(' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', list(row.values()))


def restored_active(current):
    workspace, db = Path(current['database']).parent, Path(current['database'])
    controls = Path(current['private']) / 'active-controls'
    restored = workspace / 'artifact-active-restored.sqlite3'
    backup(controls / 'observer.sqlite3', restored)
    with sqlite3.connect(db) as source, sqlite3.connect(restored) as target:
        source.row_factory = target.row_factory = sqlite3.Row
        pc = dict(source.execute('SELECT * FROM typed011_precommits ORDER BY id LIMIT 1').fetchone())
        link = dict(source.execute('SELECT * FROM typed011_moves WHERE precommit_id=?', (pc['id'],)).fetchone())
        execution = dict(source.execute('SELECT * FROM typed011_executions WHERE move_id=?', (link['move_id'],)).fetchone())
        event = dict(source.execute('SELECT * FROM events WHERE id=?', (execution['event_id'],)).fetchone())
        # Restore the exact reviewed precommit damaged by the observer control.
        target.execute('UPDATE typed011_precommits SET payload_json=?,digest=? WHERE id=?', (pc['payload_json'], pc['digest'], pc['id']))
        last = target.execute('SELECT max(id) FROM operations').fetchone()[0]
        end = next(r['id'] for r in source.execute('SELECT * FROM operations WHERE id>? ORDER BY id', (last,))
            if r['action'] == 'typed011_executor_receipt' and json.loads(r['details_json']).get('move_id') == link['move_id'])
        insert_row(target, 'events', event)
        for r in source.execute('SELECT * FROM request_keys WHERE event_id=?', (event['id'],)):
            insert_row(target, 'request_keys', dict(r))
        insert_row(target, 'typed011_executions', execution)
        for r in source.execute('SELECT * FROM operations WHERE id>? AND id<=? ORDER BY id', (last, end)):
            insert_row(target, 'operations', dict(r))
    return restored, pc['project'], link['move_id'], execution['event_id'], json.loads(execution['payload_json'])


def tamper(restored, local, event_id, workspace, kind):
    db = workspace / ('artifact-' + kind + '.sqlite3')
    backup(restored, db)
    original = Path(local['artifact_path'])
    artifact = json.loads(original.read_text())
    artifact['signature'] = '00' * 64
    path = original.parent / ('planned-' + kind + '.json')
    path.write_text(canonical(artifact))
    with sqlite3.connect(db) as c:
        c.row_factory = sqlite3.Row
        c.execute('DROP TRIGGER typed011_executions_no_update')
        changed = {**local, 'artifact_path': str(path)}
        if kind == 'signature':
            c.execute('DROP TRIGGER events_014_no_update')
            c.execute('DROP TRIGGER operations_014_no_update')
            event = dict(c.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone())
            content = json.loads(event['content'])
            content['measurement_binding']['artifact_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            event['content'] = canonical(content)
            c.execute('UPDATE events SET content=? WHERE id=?', (event['content'], event_id))
            changed.update(artifact_sha256=content['measurement_binding']['artifact_sha256'], envelope_sha256=digest(content['measurement_binding']))
            event_digest = digest({k: event[k] for k in ('project', 'kind', 'focus', 'content', 'status', 'evidence', 'parent_id')})
            # Coherently rehash the disposable copy: checksum self-consistency
            # must not substitute for the independent executor signature.
            previous = 'GENESIS'
            for row in list(c.execute('SELECT * FROM operations ORDER BY id')):
                details = json.loads(row['details_json'])
                if row['action'] == 'event_created' and details.get('id') == event_id:
                    details['digest'] = event_digest
                if row['action'] == 'typed011_executor_receipt' and details.get('event_id') == event_id:
                    details['digest'] = digest(changed)
                entry = digest({'time': row['occurred_at'], 'action': row['action'], 'details': details, 'previous': previous})
                c.execute('UPDATE operations SET details_json=?,previous_hash=?,entry_hash=? WHERE id=?', (canonical(details), previous, entry, row['id']))
                previous = entry
        c.execute('UPDATE typed011_executions SET payload_json=? WHERE event_id=?', (canonical(changed), event_id))
    return db


async def verify(current, output):
    restored, project, move_id, event_id, local = restored_active(current)
    workspace = Path(current['database']).parent
    cases = [('historical_positive', restored, 'VALID_BOUND_MEASUREMENT', None),
        ('artifact_digest', tamper(restored, local, event_id, workspace, 'digest'), 'REJECTED', 'ARTIFACT_DIGEST_MISMATCH'),
        ('executor_signature', tamper(restored, local, event_id, workspace, 'signature'), 'REJECTED', 'EXECUTOR_SIGNATURE_INVALID')]
    rows = []
    for label, db, status, reason in cases:
        parameters = StdioServerParameters(command=sys.executable, args=[str(SOURCE / 'engine017_server.py'), '--canonical', current['legacy'], '--db', str(db)],
            env={**os.environ, 'LIVE_MATH_ENGINE_017': '1'})
        with (output / (label + '-stderr.txt')).open('w') as errors:
            async with stdio_client(parameters, errlog=errors) as (read, write):
                async with ClientSession(Tap(read, output / 'artifact-wire.jsonl', 'response'), Tap(write, output / 'artifact-wire.jsonl', 'request')) as client:
                    await client.initialize()
                    reply = await client.call_tool('research_cycle_validate', {'project': project, 'move_id': move_id, 'event_id': event_id})
                    raw = reply.model_dump(mode='json')
                    value = reply.structuredContent or json.loads(''.join(c.text for c in reply.content if c.type == 'text'))
                    ok = value['status'] == status and (reason is None or reason in value['reason'])
                    rows.append({'control': label, 'result': 'PASS' if ok else 'FAIL', 'request': {'project': project, 'move_id': move_id, 'event_id': event_id},
                        'response': raw, 'basis': 'Restored exact real postmeasurement/precommit snapshot; owner fault copies only.'})
                    write_json(output / 'artifact-negative-controls.json', rows)
                    if not ok:
                        write_json(output / 'first-artifact-failure.json', rows[-1])
                        raise ValueError(label + ':' + canonical(value))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--current', type=Path, required=True)
    args = parser.parse_args()
    current = json.loads(args.current.read_text())
    output = Path(current['output'])
    start = time.perf_counter_ns()
    own, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    rows = asyncio.run(verify(current, output))
    end, child_end = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    write_json(output / 'artifact-control-costs.json', {'MCP_tool_calls': len(rows), 'initialized_clients': len(rows),
        'wall_ns': time.perf_counter_ns() - start, 'CPU_ns': round((end.ru_utime + end.ru_stime + child_end.ru_utime + child_end.ru_stime
            - own.ru_utime - own.ru_stime - children.ru_utime - children.ru_stime) * 1e9), 'peak_RSS_KiB': max(end.ru_maxrss, child_end.ru_maxrss)})
    print(canonical({'controls': len(rows), 'PASS': len(rows)}))


if __name__ == '__main__':
    main()

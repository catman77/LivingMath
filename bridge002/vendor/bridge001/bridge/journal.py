"""Append-only local software receipts with a verifiable hash chain.

Content is kept in separate retention-controlled files; journals hold hashes.
This is tamper evidence, not protection against a malicious filesystem owner.
"""
import fcntl
import json
import os

from .canonical import Refusal, canonical_bytes, canonical_hash


def verify(rows):
    previous = '0' * 64
    for index, row in enumerate(rows):
        body = {k: v for k, v in row.items() if k != 'sha256'}
        if body['index'] != index or body['previous_sha256'] != previous or canonical_hash(body) != row['sha256']:
            raise Refusal('JOURNAL_CHAIN_MISMATCH')
        previous = row['sha256']
    return previous


def append(path, event_type, input_value, output_value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+', encoding='utf-8') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        rows = [json.loads(line) for line in stream if line.strip()]
        previous = verify(rows)
        body = {'index': len(rows), 'previous_sha256': previous, 'event_type': event_type,
                'input_sha256': canonical_hash(input_value), 'output_sha256': canonical_hash(output_value)}
        row = {**body, 'sha256': canonical_hash(body)}
        stream.seek(0, 2)
        stream.write(canonical_bytes(row).decode() + '\n')
        stream.flush()
        os.fsync(stream.fileno())
        return row

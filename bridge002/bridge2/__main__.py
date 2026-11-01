import argparse
import json
from pathlib import Path

from .shared import Refusal, read_json
from .ingest import MAX_RAW_BYTES, ingest, restore_raw

parser = argparse.ArgumentParser(description='Proposed local opaque importer; no approved SUTI API/native adapter.')
sub = parser.add_subparsers(dest='action', required=True)
incoming = sub.add_parser('ingest')
for name in ('source', 'declaration', 'trust', 'state'):
    incoming.add_argument('--' + name, type=Path, required=True)
incoming.add_argument('--request-key', required=True)
restoring = sub.add_parser('restore')
for name in ('state', 'out', 'trust'):
    restoring.add_argument('--' + name, type=Path, required=True)
restoring.add_argument('--declaration-sha256', required=True)
a = parser.parse_args()
try:
    trust = read_json(a.trust)
    if a.action == 'ingest':
        with a.source.open('rb') as source:
            raw = source.read(MAX_RAW_BYTES + 1)
        result = ingest(raw, read_json(a.declaration), trust, a.state, a.request_key)
    else:
        result = restore_raw(a.state, a.declaration_sha256, a.out, trust)
    print(json.dumps(result, ensure_ascii=False, indent=2))
except Refusal as error:
    print(json.dumps({'status': 'FAIL_CLOSED', 'reason': error.code, 'detail': error.detail,
                      'proof_status': 'unverified', 'execution_permission': {'allowed': False}}))
    raise SystemExit(2)

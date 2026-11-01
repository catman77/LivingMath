import argparse
import asyncio
import json
import os
from pathlib import Path

from .pilot import run_live, run_local
from .pilot import write
from .canonical import read_json
from .intake import ROOT, intake
from .mapping import project
from .audit import audit
from .reverse import reverse

parser = argparse.ArgumentParser(description='Independent Bridge prototype; no production writes or SUTI API.')
sub = parser.add_subparsers(dest='action', required=True)
local = sub.add_parser('local');local.add_argument('--out', type=Path, required=True)
live = sub.add_parser('live');live.add_argument('--out', type=Path, required=True)
live.add_argument('--endpoint', default=os.environ.get('BRIDGE_MCP_ENDPOINT'))
live.add_argument('--token-file', type=Path, required=True);live.add_argument('--project', required=True)
inspect = sub.add_parser('inspect')
mapping = sub.add_parser('map')
for command in (inspect, mapping):
    command.add_argument('--contract', type=Path, required=True)
    command.add_argument('--source', type=Path, required=True)
    command.add_argument('--trust', type=Path, required=True)
mapping.add_argument('--candidate', type=Path, required=True)
mapping.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
if args.action == 'local':
    result = run_local(args.out)
elif args.action == 'live':
    if not args.endpoint:
        parser.error('--endpoint or BRIDGE_MCP_ENDPOINT is required; URLs are not release invariants')
    result = asyncio.run(run_live(args.out, args.endpoint, args.token_file, args.project))
else:
    envelope, raw, trust = read_json(args.contract), args.source.read_bytes(), read_json(args.trust)
    result = intake(envelope, raw, trust, purpose='local_export' if args.action == 'map' else 'local_process')
    if args.action == 'map':
        args.out.mkdir(parents=True, exist_ok=False)
        settings = read_json(ROOT / 'eval/settings.json')
        projected = project(envelope, read_json(args.candidate), settings)
        audited = audit(envelope, projected, settings, source_bytes=raw, trust=trust)
        result = {'projection': projected, 'audit': audited, 'reverse': reverse(envelope, projected, audited)}
        write(args.out / 'mapping.json', result)
print(json.dumps(result if args.action == 'inspect' else {'status': result.get('status', result.get('audit', {}).get('status'))}, ensure_ascii=False))

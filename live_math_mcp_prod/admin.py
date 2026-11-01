"""Explicit local-operator actions: approval, witness review, backup, health."""
import argparse, hashlib, json, os, sqlite3
from contextlib import closing
from pathlib import Path
from research_store import ResearchStore
p=argparse.ArgumentParser()
p.add_argument('--db',default=os.getenv('LIVE_MATH_DB',str(Path.home()/'.local/share/live_math/research.sqlite3')))
s=p.add_subparsers(dest='cmd',required=True)
a=s.add_parser('approve-policy');a.add_argument('request_id',type=int);a.add_argument('--approver',required=True)
b=s.add_parser('backup');b.add_argument('destination')
r=s.add_parser('review');r.add_argument('event_id',type=int);r.add_argument('verdict',choices=['verified','refuted']);r.add_argument('--reviewer',required=True);r.add_argument('--witness-file',required=True);r.add_argument('--notes',required=True)
s.add_parser('health')
e=s.add_parser('review-adverse-evidence')
e.add_argument('--request-file',required=True,help='JSON project/event/obligation/version/operation/disposition/reason/evidence_refs/request_key')
e.add_argument('--operator',required=True)
args=p.parse_args()
if args.cmd=='backup':
    source=Path(args.db).expanduser().resolve(strict=True)
    destination=Path(args.destination).expanduser().resolve()
    if destination==source or destination.exists(): raise SystemExit('backup destination must be new and different from source')
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Opening ResearchStore here would migrate the source before backing it up.
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as connection, closing(sqlite3.connect(destination)) as backup:
        connection.backup(backup)
    destination.chmod(0o600)
    out={'destination':str(destination),'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}
else:
    db=ResearchStore(Path(args.db).expanduser().resolve(strict=True))
if args.cmd=='approve-policy': out=db.approve_policy(args.request_id,args.approver)
elif args.cmd=='health':out=db.health()
elif args.cmd=='review-adverse-evidence':
    if not Path(args.db).expanduser().is_file():raise SystemExit('existing database required')
    request=json.loads(Path(args.request_file).read_text())
    out=db.evidence_reviews.record(**request,operator=args.operator)
elif args.cmd=='review':
    witness=Path(args.witness_file)
    if not witness.is_file():raise SystemExit('witness file does not exist')
    out=db.add_review(args.event_id,args.verdict,args.reviewer,hashlib.sha256(witness.read_bytes()).hexdigest(),args.notes)
print(json.dumps(out,ensure_ascii=False,indent=2))

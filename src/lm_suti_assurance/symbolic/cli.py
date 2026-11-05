"""Standalone symbolic commands use the same installed worker and private store."""

import asyncio, base64
from pathlib import Path
from ..core import canonical
from .executor import Executor
from .service import SymbolicService


def add_parser(sub):
    parser = sub.add_parser("symbolic")
    actions = parser.add_subparsers(dest="symbolic_action", required=True)
    for name in ("explore", "inspect", "export", "replay"):
        p = actions.add_parser(name)
        if name != "replay":
            p.add_argument("--project", required=True)
        if name == "explore":
            p.add_argument("--request-key", required=True)
            p.add_argument("--file", required=True)
        elif name in ("inspect", "export"):
            p.add_argument("--run-id", required=True)
            if name == "inspect":
                p.add_argument("--view", default="summary")
                p.add_argument("--offset", type=int, default=0)
                p.add_argument("--limit", type=int, default=32)
            else:
                p.add_argument("--output", required=True)
        else:
            p.add_argument("bundle")


def run(args):
    from ..cli import read_json

    if args.symbolic_action in ("inspect", "export"):
        service = SymbolicService(args.state_dir, None)
        if args.symbolic_action == "inspect":
            return service.inspect(
                args.project, args.run_id, args.view, args.offset, args.limit
            )
        from .bundle import export
        from ..workspace import atomic_write

        raw, manifest = export(service.workspace(args.project), args.run_id)
        path = Path(args.output)
        path.parent.mkdir(exist_ok=True, parents=True)
        if path.exists() and path.read_bytes() != raw:
            from ..errors import AssuranceError

            raise AssuranceError("EXPORT_ALREADY_EXISTS")
        atomic_write(path, raw)
        return {"status": "EXPORTED", "manifest": manifest}
    pool = Executor()
    try:
        if args.symbolic_action == "explore":
            request = read_json(args.file)
            request = request.get("request", request)
            return asyncio.run(
                SymbolicService(args.state_dir, pool).explore(
                    args.project, args.request_key, request
                )
            )
        return pool.run(
            {
                "action": "replay",
                "bundle_base64": base64.b64encode(
                    Path(args.bundle).read_bytes()
                ).decode(),
            }
        )["data"]
    finally:
        pool.close()

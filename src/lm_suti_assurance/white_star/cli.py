"""Operator CLI over the same durable facade and fixed worker."""

import asyncio
import base64
import json
from pathlib import Path
from ..core import canonical
from ..validation import parse
from ..workspace import atomic_write
from .pool import Pool, prepare
from .service import WhiteStar
from .contracts import TOOLS, check_schema
from . import views


def add_parser(sub):
    parser = sub.add_parser("white-star")
    actions = parser.add_subparsers(dest="white_action", required=True)
    actions.add_parser("prepare")
    actions.add_parser("status")
    for name in (
        "explore",
        "frozen",
        "inspect",
        "readings",
        "model",
        "export",
        "replay",
    ):
        p = actions.add_parser(name)
        if name != "replay":
            p.add_argument("--project", required=True)
        if name in ("explore", "frozen", "readings"):
            p.add_argument("--request-key", required=True)
        if name in ("explore", "readings", "model"):
            p.add_argument("--file", required=True)
        if name in ("inspect", "readings", "model"):
            p.add_argument("--run-id", required=True)
        if name == "frozen":
            p.add_argument("--common-ref", required=True)
            p.add_argument("--slots", type=int, default=6)
        if name == "inspect":
            p.add_argument("--view", default="summary")
            p.add_argument("--offset", type=int, default=0)
            p.add_argument("--limit", type=int, default=64)
            p.add_argument("--artifact-ref")
        if name == "export":
            p.add_argument("--output", required=True)
        if name == "replay":
            p.add_argument("bundle")
            p.add_argument("--offline", required=True, action="store_true")


def run(args):
    if args.white_action == "prepare":
        return prepare()
    pool = Pool()
    try:
        s = WhiteStar(args.state_dir, pool)
        action = args.white_action
        if action == "status":
            return pool.status()
        if action == "explore":
            return asyncio.run(
                s.explore(
                    args.project, args.request_key, parse(Path(args.file).read_text())
                )
            )
        if action == "frozen":
            return s.frozen(args.project, args.request_key, args.common_ref, args.slots)
        if action == "inspect":
            return views.inspect(
                s,
                args.project,
                args.run_id,
                args.view,
                args.offset,
                args.limit,
                args.artifact_ref,
            )
        if action == "readings":
            v = parse(Path(args.file).read_text())
            check_schema(
                v,
                TOOLS["white_star_record_interpretation"]["inputSchema"]["properties"][
                    "readings"
                ],
            )
            return s.readings(args.project, args.run_id, args.request_key, v)
        if action == "model":
            v = parse(Path(args.file).read_text())
            check_schema(
                v,
                TOOLS["white_star_validate_model"]["inputSchema"]["properties"][
                    "proposal"
                ],
            )
            return asyncio.run(s.model(args.project, args.run_id, v))
        if action == "export":
            from .bundle import export

            raw, manifest = export(s.workspace(args.project))
            atomic_write(Path(args.output), raw)
            return {
                "status": "EXPORTED",
                "sha256": __import__("hashlib").sha256(raw).hexdigest(),
                "manifest": manifest,
            }
        if action == "replay":
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

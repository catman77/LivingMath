# Repository Guidelines

## Project Structure & Module Organization

Source and tests live together in `live_math_mcp_prod/`:

- `mcp_server.py`: local stdio MCP tools.
- `research_store.py`: SQLite persistence, migrations, audit chains, and reviews.
- `admin.py`: operator approvals, reviews, backups, and health checks.
- `core.py` and `experiments.py`: research primitives and deterministic experiments.
- `test_production.py`, `test_experiments.py`, and `pilot_smoke.py`: automated checks.

The root ZIP is a packaged snapshot; edit the unpacked Python files. Experiment traces and reports are generated JSON; there is no separate asset directory.

## Build, Test, and Development Commands

Run setup from the repository root:

```bash
cd live_math_mcp_prod
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

There is no build step. From the source directory:

- `python -m pytest -q`: run both test modules.
- `python -m unittest discover -p 'test_production.py' -v`: run ledger tests without the MCP SDK.
- `python experiments.py --output /tmp/live-math-results`: generate reproducible traces and a report.
- `python pilot_smoke.py`: check project isolation and audit integrity.
- `LIVE_MATH_DB=/tmp/live-math-dev.sqlite3 python mcp_server.py stdio`: launch the development MCP endpoint; configure an MCP client to spawn it.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` for functions and variables, `PascalCase` for classes, and uppercase constants. Follow existing module boundaries and add type hints to public interfaces. No formatter or linter is configured; keep changes focused and avoid unrelated reformatting.

## Testing Guidelines

Tests use pytest functions and `unittest.TestCase`. Name files `test_*.py` and cases `test_<behavior>`. Use temporary SQLite databases. Cover changed behavior, especially persistence, migration, idempotency, project isolation, and audit integrity. No coverage threshold is configured. Unit tests do not establish MCP client interoperability.

## Commit & Pull Request Guidelines

There are no commits yet, so no message convention is established. Use short imperative subjects, such as `Fix ledger request validation`. PRs should explain the behavior change, link relevant issues, list validation commands and outcomes, and identify schema or protocol implications.

## Research & Operational Boundaries

Develop testable mechanisms, separate invention from adversarial checks, and retain negative results. Distinguish mathematical construction, experimental observation, and physical interpretation. Keep databases private and outside version control. Preserve independent operator approval and review boundaries; model-generated claims must not verify themselves. The server supports local stdio only.

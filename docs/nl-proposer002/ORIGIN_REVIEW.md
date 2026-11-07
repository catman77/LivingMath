# NL002 provenance specialist review

Final verdict: **no outstanding reproduced findings** after coordinator fixes.

Scope: `src/lm_suti_assurance/nl_proposal/` and additive registration/configuration in `tools/release_v01_entry.py`, relative to `08e936a`. Review was read-only for repository files. No holdout gold was opened; probes used repository fixtures, temporary project workspaces, and an explicit local provider test double with no model/network calls.

Regression verification completed on the final reviewed implementation:

- `PYTHONPATH=src python -m pytest -q tests/test_nl_proposal.py`: **12 passed**.
- `python /home/catman/.local/state/livingmath/nl002/origin_probe.py`: **PASS**. A real same-project SymbolicService REVERSE run completes through NLService, causes a different typed AST, and retains `TRACE_LINK_CHECKED`, `semantic_alignment_status=PROPOSED`, `execution_permission=false`. Frozen replay rejects seven independent, unrehashed mutations: run ID, operator trace, normalization, token budget, source reference, parsed answer, and raw provider output. Foreign-project access and incorrect symbolic snapshot hashes are rejected.
- The same probe submits twelve concurrent distinct keys to a waiting provider: exactly four are admitted, eight receive `NL_RESOURCE_BUSY`, and rejected requests produce no start journal rows. A completed-key retry succeeds while all four slots are occupied.
- `python /home/catman/.local/state/livingmath/nl002/origin_numeric_probe.py`: **PASS**. A real WhiteStar numeric run supplies a selected frame whose actual source-evidence order changes the typed AST. Exact frame/snapshot mismatch probes are rejected; frozen replay matches; semantic status remains proposed and execution permission false.

Previously reproduced defects were repaired and checked above: nested project flock deadlock during traced reservation, concurrent admission race (including idempotent retries at capacity), and replay accepting mutations of trace/request metadata not covered by the decoded-output hash. No unresolved instance remains in this reviewed snapshot.

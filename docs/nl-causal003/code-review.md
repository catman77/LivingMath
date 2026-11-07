# NL-CAUSAL-003 prepublication code review

Reviewed current uncommitted candidate in `.worktrees/nl003` against base
`7abc6d44622ab4aef43a0462d80c2f37537de179`, including the four new implementation
modules, tests, existing provenance/Workspace/decoder boundaries, the supplied TZ
and release-entry diff. This was a separate read-only reviewer; no production
calls, files or state were modified. This report is the sole written artifact.

## Conclusion

**NO BLOCKING FINDINGS.** No reproducible correctness, ownership, receipt forgery,
append-only, mathematical-status or data-loss defect was identified in the reviewed
candidate. The review is a code review, not independent human semantic adjudication.

## Verified boundaries

- `causal_service.py:43–62` resolves an owned finished NL journal record, verifies
  the result digest and frozen replay, and re-resolves each original owned source.
  Raw provider output cannot be supplied through the new MCP schema.
- `causal_service.py:64–78` resolves real project-owned symbolic/numerical runs
  outside the Workspace transaction; existing `provenance.traces` checks immutable
  result, original source bytes, input/snapshot guards and real frame/node ancestry.
- `causal_service.py:85–95` uses existing atomic Workspace CAS and transaction
  idempotency. Concurrent identical requests can compute twice but commit once;
  conflicting payloads cannot reuse the same key.
- `causal.py:111–137` mutates a copy of decoder order once for SHAM and calls the
  old move constructor with `placebo=False`. Provider inputs remain frozen.
- `causal.py:32–84,138–156` enumerates AST-only adjacent outer-quantifier swaps and
  capture-safe fresh alpha-renaming. FIFO expansion with exact AST dedup gives
  constructive shortest paths among retained reachable candidates. It reads
  neither source language nor White Star/gold to choose primitive successors.
- `finite_relations.py` implements its own typed-FOL valuation, explicitly uniform
  nonempty finite-domain enumeration, two directional witnesses, and UNKNOWN on
  incomplete enumeration. It does not call the original FOL evaluator or infer
  universal equivalence.
- `causal.py:214–225` distinguishes missing bases/incomplete structural comparisons
  from the set-difference verdict and checks actual primitive paths before issuing
  PRIMITIVE_CLOSURE_REPRODUCED. PROPOSED/HUMAN_NOT_EVALUATED and no execution grant
  remain explicit on candidates and top-level output.
- New opt-in registration preserves existing inspector metadata and dispatches
  legacy runs back to the original implementation; the release entry adds one tool.

## Scope notes, not release defects

1. Closure is bounded by depth, candidate ceiling and attempt slots. A candidate
   outside this search is not a fundamentally new operation. Preserve the parent's
   post-hoc H05 cost3 explanation separately from the preregistered depth2 arm.
2. CPU deadlines may legitimately produce REPLAY_BOUND_DIVERGENCE. This is surfaced
   explicitly instead of replacing a saved record. Thread CPU accounting correctly
   excludes neighboring MCP requests; persistence/provenance I/O is outside the
   documented decoder CPU budget.
3. SHA receipts and immutable owned journals provide byte/provenance consistency,
   not third-party provider signatures or linguistic endorsement. HUMAN_NOT_EVALUATED
   must stay visible in release claims.
4. Timing removal for replay is recursive by key name. It is acceptable for the
   present fixed schema, whose semantic nodes/witnesses retain AST/model/request
   hashes; path-scoped timing removal would make a future schema extension easier
   to audit. No exploit or current differing semantic result was established.

Validation: ran `PYTHONPATH=src <nl003 production venv>/bin/python -m pytest
 tests/test_nl_causal.py -q` on the reviewed candidate. **17 passed in1.05s**; no MCP/production mutation was used.

Recommendation: publish this developer preview because the reviewed owned-receipt,
primitive-derivation and finite-model paths preserve their fail-closed boundaries;
keep the bounded-search and unperformed human semantic checks explicit.

## Specialist supplement — testing, security and state-machine lenses

Requested follow-up on the same unchanged implementation. **No new blocking
findings.** No production actions or additional tests were performed in this
supplement; evidence below is source inspection plus independently comparing
already captured real-client artifacts.

### Testing lens

Independently compared `tools-before.json` against
`production-causal-qa/tools.json`: all **93/93 complete tool records are identical**,
94 total tools, sole addition `formal_nl_redecode`. The existing inspector wrapper
keeps its original schema/metadata and calls its previous function for non-causal
refs. Read the actual captured public check list: **60 PASS, zero FAIL**. These
captured client results are distinct evidence from the reviewer's17 local tests.
The tests exercise bounded finite comparison, five relation outcomes, alpha
capture and NOT scope, altered receipt/AST, owned project boundaries, absent
receipt, idempotency, forged trace guards and the per-thread CPU clock. This
supplement does not claim a newly executed concurrent-load test.

### Security lens and concrete threat model

The untrusted MCP caller/source/LLM output may try to forge origin, reuse another
project's objects, substitute raw output, escape AST/JSON into executable code,
reuse request keys with changed payload, or cause incomplete searches to become
mathematical/semantic admission. An owner able to rewrite private operator state
is outside the endpoint's project-isolation threat model.

The published closed input schema admits only owned NL/trace references and bounded
policy, no raw_output/AST/program/path field. NL history ownership and result SHA
are checked before frozen replay; source objects are re-resolved from formal
issuance. Real trace lookup uses the same project, original exact source bytes,
actual result/input/snapshot digests and real frame/node history. Arbitrary JSON
in a provider receipt stays data: the new path uses no eval/exec/provider/network
adapter. Existing Workspace path/reference validation and owner-only directories
remain in force, as do bounded byte pages. The new code performs no SQL migration
or mutation and does not add a write path to existing SQLite research records.

### Lifecycle/concurrency/persistence lens

A RUNNING or FAILED original NL run is rejected before counterfactual analysis.
A COMPLETED provider-unavailable run remains historical and is rejected with
FROZEN_RECEIPT_UNAVAILABLE; no reconstructed or second provider response is used.
The old NL result/bundle is read and new candidates are rebuilt rather than
editing old candidates. New counterfactual completion means that a bounded
computation ended; UNKNOWN_BOUND remains an explicit output and does not become
a mathematical or execution status.

For two concurrent requests with an identical namespaced key, both may perform
bounded CPU work outside the lock, but `Workspace.transact` rechecks the key and
payload digest under the project flock before invoking the committing callback.
Only the winner can append nl.causal.finish; the loser returns its exact saved
record. A different payload under the same key raises REQUEST_KEY_CONFLICT at
that same final check. CAS objects precede the journal commit; failure can leave
unreferenced immutable new objects but cannot expose a partially committed run.
The journal is rebuilt with prior rows, sequence/previous hash/new digest and
atomically replaced after existing hash-chain validation (`workspace.py:125–142`).
No old row or result is overwritten.

Finite enumeration exhaustion returns UNKNOWN_BOUND with an explicit reason and
retains any genuinely observed witnesses. Structural comparison with a missing
base or incomplete generation is separately NO_BASE_PROPOSALS/UNKNOWN_BOUND.
All result/candidate/response branches keep execution_permission=false; neither
successful replay, finite relation, TYPED nor TRACE_LINK_CHECKED transitions to
SEMANTICALLY_LICENSED or verified. Thus counterfactual completion cannot activate
an existing research move or grant experimental execution.

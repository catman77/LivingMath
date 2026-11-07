# Native adversarial review — NL-CAUSAL-003

Candidate: `/home/catman/CatmanCode/LivingMath/.worktrees/nl003`, compared with
`7abc6d44622ab4aef43a0462d80c2f37537de179`. Read-only review of the four new
implementation modules, their tests, existing decoder/replay, provenance,
Workspace transaction boundaries and the supplied TZ. No production calls,
state changes, provider calls or source-code changes were performed.

## Result

**NO BLOCKING FINDINGS.** No concrete receipt forgery, ownership bypass,
idempotency violation, capture, false finite-classification or semantic-status
escalation was reproduced in the reviewed candidate.

## Attack surfaces checked

- `causal_service.py:43–63` resolves the source from an owned `nl.finish` record,
  validates stored result SHA and frozen replay, and re-resolves the exact source
  object within the same project's issued formal references. An arbitrary
  client-supplied `raw_output` is absent from the closed MCP schema.
- `causal_service.py:67–78` resolves structural runs in the same project and
  delegates to actual `provenance.traces`; source bytes, result SHA, input/snapshot
  guards, frame/node references and parent existence are checked. Foreign or
  missing provenance is refused rather than replaced with a fabricated trace.
- `causal_service.py:85–95` uses existing atomic append-only Workspace
  transactions. Concurrent identical calls may recompute bounded work, but
  commit once; a differing payload reusing the key conflicts at the transaction.
- `causal.py:113–135` shuffles only decoder source order once, labels the result
  SHAM_NOT_EVIDENCE and preserves before-AST/provider input. No second placebo
  reversal or new model call is introduced.
- `causal.py:32–84,138–153` enumerates AST-only adjacent outer swaps and safe
  alpha-renaming. Constructive chains are re-derived, SHA-checked and retyped.
  Multi-source BFS visits shorter paths before longer paths. Bounded closure is
  not represented as universal completeness.
- `finite_relations.py:35–66` enumerates every relation assignment for the
  explicit uniform-domain class, retaining directional concrete countermodels.
  Model/cell/CPU exhaustion returns UNKNOWN_BOUND; finite equality never claims
  universal equivalence or linguistic licensing.
- `causal.py:214–219` does not turn missing arms, CPU-incomplete generation or
  absent typed base proposals into a negative expressivity conclusion. Both
  content and metadata retain PROPOSED/HUMAN_NOT_EVALUATED/no grant.
- `causal_mcp.py:59–71` extends old inspector dispatch while keeping published
  metadata; own-project causal references are routed to their immutable record.

## Executed local probes

1. Independent rerun: `PYTHONPATH=src .../nl003/production-venv/bin/python -m
   pytest tests/test_nl_causal.py -q` → **17 passed in1.05s**.
2. Additional adversarial alpha probe: an AST with reused binder `x` in disjoint
   scopes and a pre-existing `_alpha0` binding produces three typed renamings to
   fresh `_alpha1`. All three are SAME_ON_BOUND under an independently enumerated
   finite class. Sibling bindings remain unchanged. **3/3 PASS**.

## Interpretation boundaries

This review does not certify provider digital signatures, external human meaning,
universal expressivity or globally complete search. The recorded H05 result is
outside the preregistered depth2 closure and has an ordinary three-swap derivation;
it cannot establish a new fundamental operation or semantic advantage. CPU-bound
replay divergence is explicitly reported, and historical failure receipts remain
part of the release evidence.

Recommendation: Publish the tested developer preview because ownership, frozen
receipt, constructive AST and append-only boundaries held under the reviewed
attacks, while the finite-search and human-licensing limitations remain explicit.

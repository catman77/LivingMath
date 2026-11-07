# Formal Bridge001 service/security/state-machine review

Scope: `/home/catman/CatmanCode/LivingMath/.worktrees/formal001`, DIFF_BASE
`5c756c038fa528bc933f03e99bab0cbc402a3606`; included untracked runtime modules.
Read-only review; no source/test edits and no production actions.

Final verdict: NO OPEN FINDINGS in the service/security/state-machine scope. Two initially confirmed findings below were fixed by the parent and independently reproduced again against current code;
source_ref and duplicate-candidate problems were corrected during the review and
independently rechecked. Line numbers refer to the reviewed snapshot and may move.

## Findings and verified resolutions

1. **CRITICAL, confidence10/10 — FOL contrast ignores assumptions.**
   `formal_bridge/fol.py:128` evaluates only
   `values=[evaluate(c['formula_ast'],sig,model,bounds)['truth'] for c in candidates]`.
   Candidate `assumptions` are typechecked/stored but absent from this model search.
   With `P:x->Bool`, let both candidates assume `forall x P(x)`, and formulas be
   respectively `forall x P(x)` and `forall x x=x`. Current search returns
   `FINITE_COUNTERMODEL` on one-element domain with `P=[]`, vector `[false,true]`.
   That model violates both interpretations' assumption; the two readings agree
   wherever that assumption holds. This is not an interpretation countermodel.
   Fix: explicitly choose/document `Gamma∧phi` comparison or common-applicability
   comparison, evaluate assumptions, and include their truth/applicability witnesses.
   Never report a bare-formula countermodel as if the assumptions were respected.
   **RESOLVED:** current fol.py:128-135 requires every candidate assumption to hold, records assumption truth vectors and names comparison scope. Reproducer now returns NO_COUNTERMODEL_WITHIN_BOUND,6 models checked, equivalence_claim=false. See SERVICE_ASSUMPTIONS_RECHECK.json.

2. **INFORMATIONAL functional/provenance defect, confidence10/10 — contrast accepts
   nonexistent required run_ref.** `formal_bridge/service.py:57-61` catches
   `NOT_FOUND` from `self.candidate(w,run,ref)` and falls back to any owned imported
   grammar. The caught error also covers `self.load(w,run)` failing. In a real
   isolated-worker temporary project, two correctly stored grammar object refs and
   `run_ref='0'*64` returned `COMPLETED/DISTINGUISHING_QUERY`.
   Fix: validate the same-project completed anchor run once before fallback; use
   fallback only for a candidate-membership mismatch. Reject foreign/nonexistent
   anchor refs even when explicit candidate ASTs are locally owned.
   **RESOLVED:** current service.py:56 validates anchor=self.load(w,run) and COMPLETED before fallback. Real-worker temporary workspace repro now rejects with NOT_FOUND; no invalid contrast run is created.

## Corrections verified during review

- Advertised FOL candidate.source_ref initially used semantic digest(source), while
  owned references are blob-root refs; it was unresolvable through owned(). Parent
  preserved issued source_ref through resolver/engine/propose. Actual worker probe
  now resolves candidate.source_ref to the original exact source.
- Identical proposal entries initially produced duplicate candidate IDs, preventing
  candidate() from selecting exactly one. Parent bound IDs to derivation+index;
  duplicate entries now have distinct addressable IDs and retain alternative refs.

## Executed checks and evidence

`SERVICE_REVIEW_PROBE.json` and private reproducible `service_review_probe.py`:

- Actual existing isolated symbolic Executor READY; no whitelist changes.
- Same-project source ownership passes; cross-project source lookup rejects.
- Three concurrent identical request keys create one immutable run.
- Existing conflicting-key behavior covered by tests/test_formal_bridge.py.
- Interrupted reserved job recovered to FAILED, prior entries preserved exactly,
  complete journal hash-chain validates before/after recovery.
- Source-ref correction and duplicate-candidate addressing pass.
- Nonexistent contrast-anchor now correctly rejects NOT_FOUND after parent fix.
- Shared-assumption FOL reproducer now returns NO_COUNTERMODEL_WITHIN_BOUND; no false equivalence claim.
- Previous source-ref and duplicate-candidate corrections remain passing in the repeated actual-worker probe.

Static checks: supplied data are not executed; grammar/proof/model validation uses
fixed dispatch; source/program values are never interpolated into subprocess shell
commands. Existing shared Executor quotas and worker CPU/wall/RAM ceilings retained.
Four SQLite stores and old audit code not modified by this implementation.
Historical extension binding calculation adds formal_bridge only when directory
exists, preserving old installed profile hash construction.

Caveats: independent mathematics/CFG/DFA correctness is assigned to the other
reviewer. Public HTTPS/OAuth deployment acceptance and full old-profile replay are
not part of this isolated reviewer probe; parent must complete them separately.
No external-model or human-meaning accuracy is claimed.

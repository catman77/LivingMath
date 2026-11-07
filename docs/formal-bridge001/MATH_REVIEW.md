# Formal Bridge001 independent mathematical review — final recheck

**Status: NO OPEN FINDINGS in the reviewed scope.** Five concrete defects were
reported to the parent, fixed there and independently rerun with their original
counterexamples. This reviewer made no source/test/production edits.

Base: `5c756c038fa528bc933f03e99bab0cbc402a3606`; current worktree snapshot is
bound by `MATH_REVIEW_HASHES.json`. Original evidence and old code quotations are
preserved in `MATH_REVIEW_PRE_FIX.md` rather than overwritten as successful tests.

## Verified corrections

1. **F1, short negative pruning:** observed-center/nonnullable families retain all
   pair bindings. The original `a#b=True, ab=False, #=False` target grammar now
   exists in the actual catalog and has compatible inferred candidates.
2. **F2, assumptions:** finite-model contrast checks all candidates' assumptions
   before comparing formula truth. Formulae differing only outside the admitted
   assumption domain now yield `NO_COUNTERMODEL_WITHIN_BOUND`; no false countermodel.
3. **F3, DFA recursion:** iterative search fits the original1534-edge/256-record
   bounded case as a one-state machine,0.0223CPU seconds in this recheck.
4. **F4, catalog budgets:** the1ms original repro now returns explicit catalog
   generation/search UNKNOWN in0.00167CPU seconds instead of0.853seconds. Generation
   limits and an unmaterialized generator recipe are disclosed.
5. **F5, unknown catalog:** all out-of-domain train checks propagate
   `UNKNOWN_BOUND:UNRESOLVED_CATALOG_OBLIGATIONS`, rather than false incompatibility.

`MATH_REVIEW_RECHECK.json`: PASS_ALL_FIVE_REPRODUCERS.
`MATH_REVIEW_TESTS.log`:15 targeted tests PASS in1.93seconds on this snapshot.

## Positive checks and limits

Read CFG IR, packed least-fixed-point chart and independent verifier, DFA
constraint search/explicit transition witnesses, source/span validation, typed
FOL proposal/model/assumption handling, contrast, service and MCP wiring, and
existing tests. Independent verifier imports no producer/search implementation.
Separate start/EPS, two `aaa` derivations, no query labels in fit, model sealing,
no correct label in proposed contrast, PROPOSED/type/model-truth separation,
closed-world finite checks and no universal/unique grammar claims are explicit.

Actual HTTPS/OAuth acceptance, final release assembly and deployment integrity
remain the parent's work; this review does not claim to have executed them.

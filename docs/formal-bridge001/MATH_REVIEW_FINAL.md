# Formal Bridge001 — final range / fix check

**Status: CLEAN in the reviewed code scope.** No source/test/production changes
were made by this reviewer. This is a read-only follow-up to MATH_REVIEW.md,
focused on total synthesis-budget handling and the real QA annotation loop.

## Budget / query validation

`engine.synthesize` now starts its total budget before fitting. Query-phase
exhaustion appends explicit UNKNOWN_BOUND decisions for every remaining query,
instead of escaping Bound as an internal worker error. Each query still passes
`validate_record` before the exhaustion shortcut.

Independent direct rechecks (`MATH_REVIEW_FINAL_RECHECK.json`) passed:

-1ms budget/256 queries: all256 responses retained with decision=None and
 UNKNOWN_BOUND; no partial list or internal error.
- A hidden accepted label in the last query is still rejected with
 HELDOUT_LABEL_LEAKAGE despite exhausted budget.
- A forged source SHA in the last query is still rejected with SOURCE_MISMATCH
 despite exhausted budget.

21 current targeted tests passed in3.79s (`MATH_REVIEW_FINAL_TESTS.log`).
I read the parent's current full-suite receipts rather than extrapolating:
`FINAL_SOURCE_TESTS_V2.log`:430 PASS/41.13s;
`FINAL_INSTALLED_TESTS.log`:430 PASS/41.06s.
The older429 source log is intentionally retained as earlier evidence.

## Active external annotation audit

The QA loop selects actual retained candidate IDs from the server's frozen model,
asks formal_contrast for a real disagreement and checks that correct_label=None.
The requested word must be absent from existing train. Only then does the separate
external-annotations holder supply its label. A new dataset ref and new synthesis
request key create the next training generation; immutable previous predictions,
including enriched-pre-active predictions, remain saved.

The external annotation table covers short words of lengths0..6. The parity
holdout is length7, so those active labels do not duplicate its heldout labels.
Heldout gold labels are parsed only at final scoring. Before inference the harness
checks the sealed gold file's raw-byte SHA commitment, which does not feed labels
to fit. No production learner imports the external oracle.

## Required reporting caveat retained

The frozen regular_ab_plus enriched set has131 records:130 genuinely unseen
word values and1 previously annotated epsilon control. Do not describe all131
as blind holdout. The parent explicitly accepted keeping the frozen set intact
and splitting train-overlap/seen/unseen metrics during final postprocessing.
That reporting split is outside this code-range approval; its final artifact
must be checked before publishing claims. Pre-active failures must remain visible.

No live HTTPS/OAuth suite, production deployment or final report/asset publication
was executed by this reviewer. Their final outcomes remain the parent's work.
The reviewed file hashes are recorded in MATH_REVIEW_FINAL_HASHES.json.

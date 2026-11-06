# DYCK006 — independent scoped pre-landing review

## Final verdict

**NO OPEN FINDINGS** on the reviewed candidate. Two confirmed critical defects and one diagnostic defect were corrected by the producer during review, then rechecked independently. Final required source test command: **22 passed in 13.80s**, exit 0.

Worktree: `/home/catman/CatmanCode/LivingMath/.worktrees/dyck006`; diff base: `9d3062a`. Requirements reviewed: `03_NEXT_TECHNICAL_SPEC_RU.md`, `04_AGENT_PROMPT_RU.md`, and their original report/formal boundary. Scope: new role AST/checker/promotion, feature/learner integration, schema/MCP/service/app wiring, and `tests/test_role006.py`. This is the independent scoped review lane; endpoint, release, and deployment acceptance remain the parent's separate work.

Reviewer changed no repository source, installed nothing, and made no production, network, or model-backend calls. Only this review artifact was written.

## Confirmed defects, now fixed

### F1 — CRITICAL: unchecked producer scalar overrode independently checked proof

Original `observer_synthesis/features.py:170–176` verified the certificate but used the separate producer `result` for the feature vector and evidence. A valid negative proof could therefore accompany a positive prediction labelled `independent_status=CHECKED_INSTANCE`.

Actual control: fit the 84-word train; monkeypatch `role_ast.execute` to return `not decision` alongside its unchanged valid proof; predict `PS`. The genuine proof decision was false, while prediction returned score `0.9` with evidence decision true and independent status `CHECKED_INSTANCE`.

Fix rechecked at `features.py:175`: only `checked.decision` from `CHECKED_INSTANCE` determines the observation; other statuses produce `None`. Added `test_predict_uses_independently_checked_bit_not_untrusted_scalar` passes. This also prevents a producer scalar from turning checker `UNKNOWN` into a false decision.

### F2 — CRITICAL: query verifier action did not cross actual worker dispatch

Original `symbolic_complex/service.py:520` sent `action=role_query_verify`. `app.dispatch` understood it, but immutable `symbolic/worker.py:32–37` did not whitelist it, so real execution returned `INVALID_INPUT` before verification.

Actual fork control before fix:

```python
symbolic.worker.bounded({'action': 'role_query_verify'}, None)
# {'ok': False, 'error': {'code': 'INVALID_INPUT', ...}, ...}
```

Fix reuses existing `action=observer_verify` with `query_record`; additive `app.dispatch` distinguishes this path before the legacy feature-verification branch. Immutable worker code remains unchanged. Independent post-fix bounded-fork control returned `ok=true`, `CHECKED_INSTANCE`, and two children for `SSPPSP`. The final full test run also passes `test_query_proof_crosses_actual_immutable_worker_whitelist` through actual `Executor` workers.

### F3 — INFORMATIONAL: successful role promotion reported zero registered features

Original `learner.py:211–213` counted only legacy/context/composition promotions. The actual fitted role model reported `registered_promoted_features=0` despite one active role feature. The whitelist now includes `ROLE_BRANCHING_PROMOTION`; the scalar regression test also asserts the corrected count is one.

## Static assessment

- Generation enumerates train-alphabet role bindings, EPS/NONE bases, zero/one/two recursive calls, and instruction shuffles before full membership compatibility. There is no named Dyck predicate, arithmetic height filter, reference-oracle import, query label, or heldout-score selection in the producer.
- Program rules consume two literal role atoms, so recursive child fragments strictly decrease. The checker independently enumerates allocations for every subinterval, including negative cases. It does not import or delegate to the producer solver/catalog.
- Positive proofs verify both list-valued children, actual SPLIT/CONCAT outputs, full state contents and hashes, UTF-8 source spans, literal reconstruction, branch measures, and complete state/trace coverage.
- Canonical JSON equality and strict boolean/integer checks cover DP cells, allocations, state contents, primitive events, tree metadata, and verifier results. Closed feature/proof/node fields reject substituted claims and incomplete negative tables.
- Source/generator/evaluator bindings, train references, and feature identity remain checked independently. Query lookup selects exactly one query from the owned saved run snapshot; supplied query proofs bind that actual record and registered program/scope.
- Checked semantics and producer UNKNOWN remain distinct. The added conservative recursion-depth precheck also prevents negative DP from escaping declared depth. Independent `PPPPSSSS`/`max_depth=1` control returned producer UNKNOWN and checker UNKNOWN with permission false.
- Catalog diagnostics retain bounds, compatible AST digests, bounded untried preview, counterexamples, and incomplete-search flags without global-exhaustion claims.
- Diff against the supplied base contains no changes to immutable Symbolic, White Star, SP checker, or legacy composition checker/evaluator. Default legacy route remains separate; `auto` is the explicit additive fallback route.

## Actual execution history

Required command, always executed from the worktree:

```bash
PYTHONPATH=src /home/catman/.local/state/livingmath/generator005/production-venv/bin/python -m pytest -q tests/test_role006.py
```

| Stage | Actual result | Meaning |
|---|---|---|
| Initial source tests | 20 passed in 10.64s | Existing tests passed before the new adversarial controls; this did not invalidate the independently reproduced F1/F2. |
| Corrected candidate, before native preparation | 21 passed, 1 failed in 13.23s | Actual-worker setup failed before dispatch: `ENGINE_UNAVAILABLE_NATIVE_NOT_PREPARED`. Preserved as an environment failure, not a semantic pass or a recurrence of F2. |
| After producer's normal native preparation reported `ready=true` | **22 passed in 13.80s**, exit 0 | Includes scalar/proof-authority regression and actual worker query-proof routing. |

An additional reviewer attempt to create `Executor` before preparation likewise returned `ENGINE_UNAVAILABLE`. Direct worker startup supplied the precise missing-native-preparation reason. The producer's preparation log is `SOURCE_NATIVE_PREPARE.log` in this directory; reviewer performed no installation or preparation mutation.

Not executed by this lane: real HTTPS/OAuth MCP calls, complete repository regressions, historic production replay, SP/numerical acceptance, continuation-class experiment, packaging, publishing, or deployment. No claim of universal grammar identification or research efficacy follows from this scoped review.

## Reviewed candidate SHA-256

| File | SHA-256 |
|---|---|
| `observer_synthesis/role_ast.py` | `6b345349e2e6b936b600ee423f7bb24a7d46fcfa898b14a9e11a7c7fee1e3d58` |
| `observer_synthesis/role_checker.py` | `847654bb8cf5d69a76da8bfa22864eb15722181bfe3070870cd9088ae1ec6da3` |
| `observer_synthesis/role_promotion.py` | `31f32bfe90728dcd64f1496b9eaadb62efc99e8f8ace81aa795ff3fd36ef159e` |
| `observer_synthesis/features.py` | `339205b3c8b76036888277b84303ea6b27dd71ac7d06b51607f7f3a8c081f1a0` |
| `observer_synthesis/learner.py` | `6508c4f81e9990020391dea8ac30015437ad34b36ee3fe4c63581e0795ad18ab` |
| `observer_synthesis/contracts.py` | `20e158511d86813c3be8e2f891e6b84bc2892b9dd5e6ce57fe6f36ea9be3624a` |
| `observer_synthesis/independent_verifier.py` | `e4e7c82d2b847a49cbf023cd28907bbb95b60a8de093186075d2b7d60a323969` |
| `symbolic_complex/app.py` | `cdb651d131c2692e9eb0effb414bbf1ae9cde70f387a944300328d2ca2b629b2` |
| `symbolic_complex/service.py` | `538e601ce5c66690a159bb7128b41f045c486a1f7f55f20ce3653d4a2ffc6982` |
| `symbolic_complex/mcp.py` | `809b8f1822a3fe14b4c81d4fce7ace17c39351ae8aefc8351d967c14ebf23402` |
| `tests/test_role006.py` | `3d47fd3570dec0b10dbf5a0e406223bb40f90ce8f18ce492ef6a4ce9425578ed` |

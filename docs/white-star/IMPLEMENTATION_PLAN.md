# White Star MCP implementation plan

Goal: integrate the supplied unchanged White Star/CAD/UDAV algorithm into the existing MCP, with real matched frozen-input Bridge execution and private offline replay.

Architecture: versioned wrappers use existing Workspace journal/objects; chunk large objects without changing old limits. Fixed isolated processes load only supplied code and precompiled native library. New MCP contracts are additive. Production64 existing input schemas, frozen assurance core, approvals, SQLite and tunnel remain intact.

1. Preserve source manifest and pass original21+8 tests in a clean copied archive. Freeze actual baseline and two fixture protocols before integration.
2. Add strict request/reading/model contracts and address validation; frozen vendor integrity; build native once. Test bool/float/NaN/unknown fields, references, source/spans and expanded atlas limits before numeric search.
3. Add bounded worker with2 concurrency/16 queue,512MiB/5CPU/6wall profile; prewarm imports separately, fresh native state per job. Test isolation, failures, timeout, budgets and both exact baseline trajectories.
4. Persist RUNNING then COMPLETED/FAILED/INTERRUPTED append-only; reserve project+request key atomically. Chunk large results, stable pagination, private rights policy and replay. Test concurrency/restart/cross-project/tamper/idempotence.
5. Execute actual existing assurance facade on common_snapshot without extraction; preserve concept order/evidence and hypothesis status. Expose backend identity/losses and matched-input comparison, never native SUTI claims.
6. Generalize supplied rational operations for3 model families,1..8 matrices/256bit fractions; cyclic2x2 only. Bind registered reading/frame/source refs, preserve unsupported and negative results.
7. Register6 specified plus frozen ingress/replay tools on the same SDK. Test outputSchema/structuredContent/isError, no false readOnly mutations,64 old input schemas. Run real HTTPS/OAuth on two inputs and four identically instructed client decoder packets; distinguish fixture encoder and actual decoder receipts.
8. Run all old/new tests, source/hash checks, offline no-network replay. Stage, test rollback, back up4SQLite and allfileworkspaces, deploy exactlayer/restart HTTP only, real MCP QA at originalURL, verify all original rows/prefix/files. Deliver source/wheel/reports/transcripts/replayZIP/SHA/rollback.

Execution is inline; the supplied detailed TZ and owner's direct implementation/deployment instruction authorize this plan. No new mathematical mechanism, source rewriting or human acceptance is inferred.

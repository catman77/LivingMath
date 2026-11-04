# CLI reference

All commands accept `--state-dir DIR` **before** the command. The default is `$XDG_STATE_HOME/lm-suti-assurance` or `~/.local/state/lm-suti-assurance`. State directories must belong to the current user and deny group/other access. Linux `flock`, fsync and atomic rename provide single-owner local durability; NFS and multiuser writes are unsupported.

| Command | Required input / result |
|---|---|
| `project new` | `--project`, `--request-key`; creates an isolated workspace |
| `source add` | project/key, `--snapshot` exact SourceSnapshot JSON, `--policy` publication-policy JSON |
| `task import` / `task draft` | project/key, `--file` typed task envelope; DRAFT, no inferred fields |
| `task review` | project/key, `--task-ref`, nonblank `--actor`, `--reason`; freezes entire exact task |
| `candidate import` | project/key, `--file` candidate envelope; retains raw `candidate` or `delta`, optional `supersedes` |
| `check` | project/key, `--candidate-ref`, optional `--engine direct\|compiled`; appends decision and witnesses |
| `report` | project, `--format text\|json`; all checked candidates including rejection |
| `export` | project, `--audience private\|reviewers\|public`, `--output`; deterministic data-only ZIP |
| `replay BUNDLE --offline` | optional engine; verifies core/file/chain hashes and recomputes each decision |
| `doctor [--smoke]` | installed version, core identity, optional manual end-to-end cases |
| `examples --output DIR` | creates an explicit input directory; optional `--project` |
| `smoke [--output DIR]` | five fixed acceptance cases, model-free |

Machine schemas: `src/lm_suti_assurance/schemas/`. Original candidate/source/decision schemas remain in the one `_frozen/` island. New envelopes use `/0.1`; unknown versions return HOLD/MIGRATION_REQUIRED. A task draft is already structured input; natural-language translation and hosted proposer are optional and **not implemented** in this release.

A request key is required for every mutation. Retrying exactly the same action/payload returns the original result; changed content raises REQUEST_KEY_CONFLICT, including raw whitespace changes. New candidate/result requires a new key. Mathematical REJECTED/UNKNOWN is a completed check (CLI exit 0); transport/rights/dependency/version errors exit 2. `doctor`/smoke FAIL exits 1.

MCP equivalents use `assurance_*`; JSON files become explicit `artifact_json`, `snapshot_json`, `publication_policy_json` strings. `assurance_contract` publishes full schemas and valid proposal/policy examples. Export/replay transfers base64 ZIP data, never caller-selected server paths. Existing 44 tools retain their input schemas. Owner OAuth scope `research` is required; no operator/execution API is added.

Reports expose actual checked v0.1 `decision_artifact` and `witness_artifacts` envelopes and validate them against the published schemas. Their `value` is the unchanged original core record; the raw `decision`/`witnesses_and_countermodels` fields remain available for compatibility. No wrapper changes the logical digest or status.

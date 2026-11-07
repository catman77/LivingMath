# NL-CAUSAL-003 documentation audit

Read-only review of the uncommitted release candidate in `.worktrees/nl003` against
base `7abc6d44622ab4aef43a0462d80c2f37537de179`. No product, AGENTS.md, Git or
production files changed. This is a native documentation review; it is not external
human semantic adjudication and does not claim the full gstack candidate-token
protocol was executed (no candidate JSON/audit id was supplied).

## Findings requiring factual correction

1. **P1 — current schema download actually contains only83 tools.**
   `docs/MCP_INTERFACE.md:36–40` calls its linked `symbolic-v1/patch005/MCP_TOOL_SCHEMAS.json`
   the full input/output schemas and latest real production listing. Reading that
   JSON yields83 tools; this release's actual SDK listing has94. Publish/copy
   `production-causal-qa/tools.json` as the new release's schema artifact and point
   this current-reference paragraph at it. Preserve the older asset as historical.

2. **P2 — current counts disagree across navigation and registration table.**
   `README.md:37` still labels the MCP link “93 инструмента”; `README_QUICKSTART_RU.md:72`
   says production entry combines93. `docs/MCP_INTERFACE.md:58` reports total93 and
   omits the one causal registration row, although its header correctly says94.
   Change these current counts to94 and add the causal tool/module row. The
   historical91/93 statements in the explicitly historical NL002 description may
   remain, ideally with a dated heading instead of suggesting the current count.

3. **P2 — reconnection advice still points at a deleted previous origin.**
   `docs/MCP_INTERFACE.md:40–42` says reconnect “по тому же URL”; `:393–395` says
   “по прежнему URL” if the client sees91 tools. The new report correctly documents
   that the old Cloudflare origin was deleted. Update this current advice to the
   actual new URL `https://difficulty-nightlife-rca-missions.trycloudflare.com/mcp`
   (or direct the reader to the current origin above) and expect94 tools after
   initialize/tools/list. A cached old URL cannot be repaired by tools refresh.

4. **P2 — slot count is parameterized, not always8.**
   `docs/nl-causal003/QUICKSTART_RU.md:76` states each arm has8 attempt slots, then
   documents policies with1..8 candidates. In `causal.py`, slots are `range(cap)`
   where cap is `max_candidates_per_source`. Clarify “8 in this example; generally
   max_candidates_per_source equal attempt slots per arm.” The reported experiment
   did use8; no result/counter correction is needed.

## Evidence verified

- Source and installed-wheel logs each contain464 PASS; focused suite contains17.
- Actual public SDK listing contains94 tools; all93 previous full tool records
  (schemas, annotations and descriptions) equal the captured baseline.
- Public causal result is60 PASS; public Formal Bridge result is869 checks and
  667 MCP calls. The four declared control families total1024/1024.
- Twelve old runs have actual replay receipts;17 structural runs were recomputed
  and match original result SHA. Source/kernel and SQLite/journal preservation
  reports agree with the release report.
- Both fresh provider receipts are OK gpt-6.1-sol, tools_used=0, one call each and
  six source-only items each. Corpus/rubric byte SHA matches PRECOMMIT.json.
- New sample has9 no-incremental results,2 NO_BASE_PROPOSALS and1 H05 outside
  depth2. H05's separate post-hoc3-swap derivation is explicitly outside the causal
  budget comparison, with no semantic-benefit claim. Finite-only truth comparisons,
  PROPOSED/HUMAN_NOT_EVALUATED and execution_permission=false remain distinct.
- Exact JSON example matches the MCP schema and real owned project/source/trace
  references. All local Markdown links in the audited files resolve.
- Intended forthcoming GitHub release URLs were not treated as already published.

## Coverage map and scope

| Surface | Reference | How-to/tutorial | Explanation |
|---|---|---|---|
| formal_nl_redecode | MCP_INTERFACE/QUICKSTART | exact JSON and inspect pages | ARCHITECTURE/RCA |
| offline replay | QUICKSTART | CLI invocation/trusted SHA | replay divergence and finite bounds |
| production change/rollback | USER_REPORT/DELIVERY | QUICKSTART rollback | preserved SQLite/CAS/history |
| experimental verdict | TEST_MATRIX/result/table | open-control references | human-adjudication and depth2 limits |

No zero-coverage feature was found. The existing Mermaid diagram does not explicitly
show the new causal route; the added architecture section supplies its module/data
flow and explains that it never calls the provider. This is advisory diagram debt,
not a renamed/missing existing diagram component.

**Outcome:** factual documentation fixes requested above; no scientific-overclaim,
missing evidence, broken local link or additional code defect identified by this audit.

## Re-audit — PASS

All four requested factual corrections have been applied and verified in the final
candidate. The earlier findings above are retained as review history and are now
**CLOSED**. Current published-schema artifact is byte-identical to the actual
production SDK listing (94 tools; SHA
`9fcc7c65600ac5a174c726f50263ea5812a29506819624731f36973647440916`).
Navigation/current-registration counts now read94, the causal registration row is
present, and both reconnect paragraphs point to the current origin and expect94.
The attempt-slot text now correctly states max_candidates_per_source (8 in this
example). The Mermaid diagram explicitly includes the causal route, frozen receipt
and finite checker. CSV is LF-only; staged diff --check is clean.

**Final outcome: PASS. No remaining documentation findings.** This remains an
engineering documentation review, not human semantic licensing. No product docs,
AGENTS.md or production state were modified by the reviewer.

Verified final-file SHA256:

```json
{
  "README.md": "d5ded7bc253ca638cab9cd7d45e5c1a34f770714dba1e6d23e1c0a8dd9bb26a7",
  "README_QUICKSTART_RU.md": "e49d85527646af2ff32e7ce6a6ee6cfb3d2d433ab9d9d7c3dfa11ab63b4d6d76",
  "docs/MCP_INTERFACE.md": "c4989c82d7aaae88873459d2b1d980825dd5dcd29bb6a40d59768ad39b81900e",
  "ARCHITECTURE.md": "5277ed9cba629d8a2c33ba1e8ecddfaa4f139c633c2db945220b39a4c509f2e5",
  "docs/nl-causal003/QUICKSTART_RU.md": "5242f8297213ed527333df228f5fa3abf2b68d58453b154014d6b1349c5ec444",
  "docs/nl-causal003/MCP_TOOL_SCHEMAS.json": "9fcc7c65600ac5a174c726f50263ea5812a29506819624731f36973647440916",
  "docs/nl-causal003/HIDDEN_RESULTS_TABLE.csv": "83a6e5058343e325c6aae4446241a4265e05fd7eb9db7540b5e0339c3094b16e"
}
```

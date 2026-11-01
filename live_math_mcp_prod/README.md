# LivingMath runtime

Current unified source version: **1.2.0rc4-meaning014-experimental**.

See the [repository README](../README.md), [installation guide](../docs/INSTALL.md),
[usage and exact ingest examples](../docs/USAGE.md), and [testing guide](../docs/TESTING.md).

The unified HTTPS/OAuth server exposes 44 MCP tools through
`python -m unified_system.local serve`. The separate `mcp_server.py stdio`
entrypoint is the legacy ledger interface, not the combined system.

The ledger component retains its own 0.4.2 schema/lifecycle contract.
The Meaning014 experiment has no demonstrated gain over equally informed B+;
see [research status](../docs/RESEARCH_STATUS.md).

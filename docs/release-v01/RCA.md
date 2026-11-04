# RCA

## Resolved issues

- Existing public quick tunnel had lost registration: `Unauthorized: Tunnel not found`; the old hostname no longer resolved. Backed up all4 stores and service configuration, restarted the owner tunnel wrapper, then tested its new public TLS/OAuth origin.
- Initial test driver compared issuer with no trailing slash, whereas the actual Pydantic-normalized issuer is exactly origin plus `/`, with exact origin/token and origin/authorize endpoints. Corrected the assertion; original FAIL retained in mcp/initial-issuer-test-failure. No OAuth validation was weakened.
- Initial historical-regression adapter forgot intentionally wrong expected verifier digests in fixtures C07/D23. Passed the original fixture parameter rather than altering expected HOLD or core bytes.
- Export guard initially missed credential keys inside nested JSON strings. Added recursive decoded-value inspection and concrete credential/email/phone/path tests. Full negative source proposals remain private; they are not silently redacted/repaired.
- Untrusted embedded schema references/regex could cross an offline boundary. Preview now accepts only the two existing reviewed SUTI schema source SHAs and checks schema-source kind. Unregistered schemas return HOLD; no synthetic evaluator/DSL was introduced.
- MCP replay originally caught AssuranceError (a ValueError subclass) in the base64 handler, hiding a real bundle/dependency cause. Split decoding and replay error handling. Unit and real-public-MCP regressions confirm INVALID_BASE64 and INVALID_BUNDLE remain distinct. Final runtime layer exactly matches the accepted staging manifest.
- Future inner candidate/delta versions now explicitly return HOLD/MIGRATION_REQUIRED. Raw proposals and their rejection/hold records remain append-only.

## Unclosed final-release evidence gate

R3 requires two real external technical people to replay from README without the original model. None has provided a report. Three pilot bundles and an evidence form are supplied. Minimum next action: two actual independent runs and retained raw output, including failures/manual steps. No code weakening, fabricated people or new model benchmark can substitute this evidence. Until then final readiness remains PENDING; the owner-operated preview is installed and tested.

## Scope

No mathematical truth inference was added. No PROVED_FORMAL/verified assigned. Source attestation does not establish physical truth or execution permission. Native SUTI NOT_EXECUTED; formal adapter UNAVAILABLE_NOT_REGISTERED. Full raw operator backups/tokens/configuration remain outside this distribution.

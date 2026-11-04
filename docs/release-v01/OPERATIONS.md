# Backup, update and rollback

Before touching production, use SQLite Backup API for canonical, typed, OAuth and DAV stores with read-only sources. Record integrity checks, original paths/inodes, per-table row digests, events, obligations, status history and audit prefix. Keep backups/configs/tokens owner-private outside Git. Per-store live backups are not an atomic multi-store transaction; for a point-in-time coordinated restore stop writes before capturing all stores.

Build a new immutable code layer, hash every file and keep the old layer/venv/drop-ins. Rehearse on copied databases, with inference disabled, before promotion. The additive assurance workspace uses separate file state; it does not replace research SQLite. Do not initialize empty research databases during upgrade.

Production switch: add an owner-private systemd ExecStart drop-in pointing to the SHA-checked release entry/config; preserve existing DB paths/inodes and accepted legacy source approvals. Restart the HTTP service, test health and tools/list through real external HTTPS/OAuth, then run only dedicated assurance QA projects. Recheck original data rows and audit chains. The accepted typed startup reconciles outstanding typed grants; preserve its append-only evidence and report any changes.

Rollback code by restoring the preceding ExecStart drop-in/config, daemon-reload and restart. Do not restore older SQLite copies over a live database: this discards subsequent writes. If data recovery is necessary, stop services, retain failed files, restore backups using SQLite Backup API into the same authorized paths, verify integrity, row counts/audit prefix and inode requirements, and obtain independent operator review for any reconciliation.

A dead Cloudflare quick tunnel requires a fresh tunnel and origin. Update the origin selected by the existing owner service, then reconnect the ChatGPT app to the newly printed `/mcp` URL and approve owner OAuth. Preserve OAuth history; do not expose login passwords in reports. Staging and production traces must say whether public TLS was actually verified.

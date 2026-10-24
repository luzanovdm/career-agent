# Canonical storage and recovery

`Data/career.sqlite3` is the sole career-state owner for a workspace of one person. Foreign keys, one revision and one domain transaction bind entities, dependencies, immutable selections, receipts and durable changes. There is no JSON shadow database or editable spreadsheet import path. Schema-1 historical files are handled only by the separate offline importer.

`Objects/<sha256>.<extension>` stores immutable bytes once. Plans publish through exclusive staged files, fsync and no-overwrite links, then validate again before commit. Duplicate content is reused by hash. Selected versions and actual historical activity retain exact packet/version pins. Integrity errors retain records and report MATERIAL_CHANGED rather than silently recreating content or declaring prepared.

Expected revision prevents stale writes. request_id provides exact idempotent receipt lookup after a lost response. A plan staged under different code must be replanned. A confirmed state commit survives export failure. Derived projection caches, view fingerprints and integrity notification metadata are reconstructible and never constitute permission, sent history or semantic review.

Transaction backups use SQLite online backup. An explicit portable backup includes the revision-bound database, every registered object and a hash manifest. CSV/XLSX/profile/read-only snapshots are generated into new derived view directories; previous views and user edits are preserved. Exported CSV formula-like text is escaped and XLSX cells are inline strings. Rendering is outside interactive transaction latency measurements.

The offline importer inventories all source files, stores original records, normalizes supported historical pin/reference shapes, validates every byte hash and records each unresolved reference/semantic decision in quarantine. It does not trust historical readiness flags or infer employer permission. Strict acceptance remains blocked by quarantine. Source and destination are distinct, source fingerprints are rechecked, and the source remains authoritative until an accepted handoff. Code rollback does not mean business-data rollback; retain the full verified pre-migration source backup separately.

There is no at-rest encryption guarantee. Keep workspaces in an appropriately protected private directory. The local app uses run-scoped authentication and private current-user control; it does not create a provider account, send telemetry, configure a firewall or retain credentials.

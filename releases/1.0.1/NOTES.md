# Career Agent 1.0.1

Fix unbounded automatic database backups: atomic validated checkpoints, bounded retention (latest ten plus seven daily points), disk-space preflight and safe retry after interrupted backup. Older unmanaged snapshots/manual exports are preserved; existing oversized backup directories require separately approved cleanup.

Also includes the previously locally accepted portal corrections: all saved person/case packets, exact historical versions and sent-pin status, bounded career evidence and private context, explicit saved interview dialogue, retained unlinked observations, track save fields, and export freshness/downloads. Browsing never changes primary selection or sending history. No automatic interview generation, research or transmission. Exact n8n/B2B identifiers are not treated as numerical achievements; real metric checks remain.

Only macOS arm64 has native installation evidence. Python3.13.17, prebuilt React Aria assets and dependency licenses are bundled; no Python/Node installation is needed. Public v1.0.0 is unchanged. Code updates do not migrate business data or automatically delete historical backup archives.

## Existing installations and disk recovery

The unbounded-backup defect affects the shared1.0.0 runtime, not one user's configuration. Updating to1.0.1 prevents new unbounded accumulation; it does **not** guarantee automatic recovery of already occupied disk space. Older snapshots remain unchanged and outside automatic rotation.

Before resuming writes after an update, use read-only filesystem tools to report free bytes, database size and aggregate count/size of Backups/r*-*.sqlite3; do not trigger another full backup for diagnosis. Low space requires holding writes. A cleanup dry run should enumerate exact paths, sizes/identities, proposed bytes and the verified recovery points/portable/original archives to preserve. Explain the lost intermediate rollback granularity, obtain separate approval for that exact deletion set, then verify recovery/readback and actual free space. No cleanup command or automatic deletion of older archives is introduced by this release.

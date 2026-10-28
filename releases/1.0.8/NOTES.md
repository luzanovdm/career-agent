# Career Agent 1.0.8

This patch corrects numeric evidence parsing at list, paragraph and dated-record boundaries, so adjacent prose is not treated as a year or quantity unit. Real wrapped units, including unknown units, remain checked. Bounded ratio/duration and explicit point-scale grammar preserve numeric values and scale denominators. English/Russian month-year syntax preserves month precision through translation; changed months, years, units, percentages and unsupported quantities still fail review.

Separate exact coverage spans keep their paragraph boundaries during numerical comparison. Coverage dispositions, original claims, source evidence, immutable documents and historical transmissions are not rewritten. Numeric audit policy 8 requires normal re-review of older packets; installing this patch does not automatically approve them or grant sending permission.

Verified macOS arm64 archive only, tested on macOS 27.0.1. The declared macOS 11.0 minimum remains untested; other platforms are not certified. Existing workspace format and schema are unchanged. Complete bootstrap installation, upgrade and code-only rollback retain the bundled Python, prebuilt UI, skill guidance, dependencies and licenses. No sender, hosted service, telemetry or automatic migration is added.

Storage advisory carried forward: existing unmanaged legacy snapshots are never silently deleted. Portable/manual/migration backups remain outside automatic rotation.

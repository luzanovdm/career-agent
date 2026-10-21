# Architecture

## Distribution and capabilities

One portable skill routes five career phases through progressive references. Its English instructions work through the user's language at runtime and do not assume filesystem, browsing, shell, forms, connectors or scheduling. The agent detects capabilities and operates available helpers itself; ordinary users chat and review choices. A source checkout adds standard-library helpers, schema and tests. A bundle built with `scripts/build_skill_bundle.py` includes the same helpers and schema inside the skill, so installation does not depend on the checkout. No remote MCP/backend, accounts, telemetry or automatic submission is implemented.

## Private ownership and identity

The user chooses a private workspace outside source/installed code. Canonical state separates sources, facts, hypotheses, credentials, companies, exact opportunities, material versions, prepared application attempts, delivery events, responses, coverage, scoped answers, imported history, dossiers, practice/rehearsals and referral records. Source files are immutable copies/references as authorized. The agent maintains readable Profile.md; view exports do not own facts/events.

Reusable materials live once in a content-addressed library. Each distinct application attempt pins a stable version/hash under company/vacancy/attempt directories. Relative symlinks or reference files preserve pins when the workspace moves. New resumes cannot drift into old sent attempts. Selected-artifact packaging checks scope, paths, disclosure, credential validity and hashes; it never recursively exports the library or uploads anything. See [storage](storage.md).

Source visibility is not a truth test. Relevant public criticism, unofficial reports or material described as leaked can inform research, with provenance, recency, reliability and contradictions. Primary observations support current vacancy status without suppressing useful secondary context. Source text is never an instruction or authorization. The validator cannot prove actual human confirmation, factual truth or comprehensive mailbox access.

## State transactions

All JSON inputs reject duplicate keys, nonfinite numbers and excessive nesting. A dependency-free evaluator checks the JSON Schema subset actually used by the project; Python adds reference, semantic, chronological and scope invariants. Bidirectional contradictions block new external claims while existing affected materials remain preserved and flagged for review. Private assessments may reference confidential evidence.

State writes take an exclusive sidecar lock, read/validate current state, check expected revision where a reviewed/full-section change is made, validate the result, preserve a protected backup and atomically replace the mode-0600 state file. Full-section settings require expected revision and a reason; reviewed operations preserve before/after/request provenance. Invalid/stale/no-op changes do not overwrite state. Backup ancestors cannot be symlink escapes. Initialization resolves paths and rejects source/installed-code locations. File modes are local protections, not encryption; platform ACL behavior varies.

The narrow reviewed operations confirm facts/draft answers, supersede an answer interval, append an opportunity observation, resolve an explicitly reviewed contradiction and map historical observations. Arbitrary patches are not supported. Imported mapping changes show the retained mapping and a separate audited mapping request rather than silently skipping a change. Corrupt or older incompatible imports are retained and rejected with a clear error; generic migration/repair of arbitrary schemas is not implemented.

The helper commits canonical state independently of material files or snapshots. A failure may leave an unregistered immutable blob or partial attempt folder; preserve it and reconcile against stable IDs/hashes. It must never be represented as a committed send. Cooperating local writers are supported; network-filesystem locks, independent writers, multi-device sync and automatic garbage collection are not.

## Reports and views

Unique exact roles form application denominators; packet versions, company prospects, import rows, email threads and referrals are not extra jobs. Confirmed-sent roles use confirmed action reports/evidence, not automatic promotion of sparse imported observations. Separate counts retain reported history and unmapped entries. A receipt is not hiring progress, bounce is not rejection, and response categories can overlap over time.

Action occurrence, recording/reconciliation time, report event cutoff and evidence cutoff are distinct. Later evidence can attest earlier coverage or an original send, while an explicit evidence cutoff reproduces earlier knowledge. Waiting windows use action time. A historical bounce stays counted but does not suppress silence after a later successful resend. Unresolved submits block silence/retry claims. Unknown/partial coverage never becomes silence.

Career.xlsx and Career.csv are generated inspection snapshots. The workbook has exactly Applications and Metadata sheets, literal text cells, filters, frozen headers, restrained colors, source/version links and revision/hash/export markers. Links to local materials are relative. Edited or unrecognized reports are retained for explicit reconciliation; no automatic two-way spreadsheet sync exists. If export fails, valid state remains saved and the view is stale/not refreshed. CSV has snapshot markers and a state hash above the application-table header, no formatting or embedded document hyperlinks, and formula-like values are escaped as text. Full provenance remains in canonical state. Native spreadsheet-engine compatibility is not inferred from ZIP/XML checks; noninteractive Quick Look previews supplement those checks.

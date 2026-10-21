# Private storage and readable views

The user chooses the workspace in conversation. A friendly suggestion is their Documents folder / Career Agent; there is no automatically applied default path. For multiple people or distinct profiles, suggest separate named subfolders and show which one is active before writing. The agent reuses the chosen path, records it in handoffs and never silently switches or merges profiles.

The private workspace is outside both the distributed source and installed skill. The helper rejects initialization/mutations inside its resolved source directory, including symlink paths. Hosts writing files without the helper must enforce the same separation. Never create a real candidate workspace or import personal history as part of source development.

| Path within the selected workspace | Responsibility |
| --- | --- |
| `Profile.md` | Human-readable current career profile, directions, confirmed evidence and material unknowns; agent updates it from canonical records |
| `Originals/` | Original resume/source copies only when authorized; otherwise record references to user-managed originals. Do not modify originals |
| `Materials/objects/` | Central immutable reusable material versions by hash; unchanged resumes are stored once |
| `Applications/<company>/<vacancy>/Attempts/<attempt>/` | Distinct attempt with version/hash pins, relative symlinks/reference files, Letters, Forms, Evidence and Correspondence |
| `Applications/<company>/<vacancy>/Research/` | Shared vacancy dossier, interview preparation and source context |
| `Data/state.json` | Canonical structured facts, event history, scoped answers, imported observations and provenance |
| `Data/report-index.json` | Exported view fingerprints, state revision/hash, report cutoff and export time |
| `Career.xlsx` | Generated workbook: Applications and Metadata sheets, readable values, links, filters and frozen header; no macros or executable formulas |
| `Career.csv` | Plain application table with snapshot markers/state hash above its header; no formatting or second metadata sheet |
| `Backups/State/` | Mode-0600 state backups before validated helper mutations, in a mode-0700 local directory |
| `Backups/Views/` | Retained previous generated views when an unchanged prior export is refreshed |

Company/vacancy/attempt names combine safe readable slugs and stable-ID digests, with identity markers to reject collisions. Dates or titles alone never establish identity. Repeated applications get distinct attempt folders. Relative symlinks/reference records survive moving the entire workspace; no silent binary-copy fallback or moving “latest” resume is used. PDF generation is deferred until needed. Packaging explicitly selected material slots verifies hashes and rejects escaping links/private evidence; it never recursively includes the library.

Applications shows one row per exact opportunity, with company/role, direction, fit questions, observed pay, application stage, latest response, next action, dates, posting and document-version links. Missing values stay unknown. Imported history is clearly reported/observed, rather than promoted to confirmed delivery. Metadata holds stable IDs, sources, revision/schema/hash and export time. It is visible and provides no security boundary. Private fact banks and full event logs stay in structured state; no secrets or full email bodies belong in views.

The workbook is a snapshot, not a second database. The agent checks its previous fingerprint and current state revision/hash before refresh. If it has been changed outside the agent, leave the edited file intact, explain that it differs, and ask how to reconcile; do not overwrite it or import statuses as provider proof. If the user wants a fresh export, retain the edited copy under a user-approved name first, then export and update the fingerprint. There is no automatic two-way spreadsheet synchronization.

State commits and view exports are separate operations. If the view fails, retain valid state and explicitly say that the view was not refreshed. An absent/outdated fingerprint is stale/unknown, never proof the workbook is current. A matching revision alone is insufficient if canonical state was edited: the state hash must also match. If export itself changes a report and fails before its fingerprint is recorded, the next attempt preserves that unrecognized file for review.

To relocate, the agent pauses writers, confirms the destination, copies the complete workspace including originals/references, artifacts and backups, verifies canonical state/hash and referenced paths, then asks which location should be active. Keep the old copy until the user agrees otherwise. Absolute source references may need a reviewed update; never delete originals or silently merge histories. To switch profiles, select the other workspace and validate its state instead of reusing the current person's cached answers.

No author server receives data. The chosen AI host and connectors still process data used through them. File permissions are local protection, not encryption; Windows permission behavior depends on the host. There is no automatic cloud sync. Plain chat has no automatic file persistence: offer an explicit handoff/export and ask for import in a new session. Include the active workspace location and last successful view revision in that handoff.

# Developer and agent operations

Ordinary users install/load the skill, provide documents and converse. They do not run these commands or edit JSON. Agents with authorized shell/file capabilities can use the optional helpers; all helpers use Python 3.10+ standard library. Career helpers have no network or sending implementation; release maintenance reads only fixed public GitHub metadata/assets and uploads no candidate data. Keep private records outside the source checkout and installed bundle.

## Validation

```sh
python3 -B -m unittest discover -s tests -v
python3 -B scripts/career_state.py validate tests/fixtures/synthetic-state.json
python3 -B scripts/career_state.py stats tests/fixtures/synthetic-state.json --as-of 2026-01-15T12:00:00Z
```

Tests use synthetic people/domains and temporary private workspaces. They cover exact roles, preparation/send distinctions, contradictions, typed/scoped answers, uncertainty, event/evidence times, delivery responses, history import, credentials, transactional updates, immutable materials, safe paths, packaging and view preservation. The JSON schema subset evaluator is tested alongside semantic validation; it is not a general JSON Schema implementation. Other dialect/features need explicit support before adding them to the published schema.

## Workspace and state

```sh
python3 -B scripts/career_state.py init-workspace /chosen/private/workspace
python3 -B scripts/career_state.py put /chosen/private/workspace/Data/state.json sources /private/agent-prepared-source.json
python3 -B scripts/career_state.py settings /chosen/private/workspace/Data/state.json profile /private/agent-prepared-profile.json --expected-revision 1 --reason "Reviewed intake choices"
python3 -B scripts/career_state.py review-update /chosen/private/workspace/Data/state.json /private/reviewed-operation.json --expected-revision 2 --reason "Confirmed exact wording in conversation" --user-confirmed
```

`init` can create a single empty state file at an explicit private path; `init-workspace` creates the readable folder layout and Profile.md. Neither overwrites existing state/workspace content. `put` appends a validated record or merges duplicate source observations under the same ID. Reviewed updates support only the named narrow operations in [state format](../references/state-format.md). `--user-confirmed` attests an actual decision; it cannot manufacture permission.

`control STATE start|pause|resume|stop --evidence TEXT --user-confirmed` records real research choices; start requires `--scope`, and start/resume require a fresh live `--context-id` (optional bounded `--expires-at`, four-hour default). `research-check STATE --context-id ID` returns 0 only for that current unexpired run with resolved target/pay/schedule/other-constraint decisions; 3 means disabled, 2 means a CLI error. `reconcile-session STATE --context-id ID --expected-revision N --evidence TEXT` safely revokes stale/unknown contexts; `--interrupted` handles a known interruption even with the same token. No network work is performed by these commands. A kill may leave active flags on disk; the next context fails closed without needing that killed process to clean up. A current explicit request to start/continue research is already the user decision; record it without asking for the same approval again. Live continuation reuses one bounded run, while source/history inspection and saving drafts remain available during pause.

`answer-get STATE QUERY.json --at TIMESTAMP` returns only confirmed, unexpired exact meaning/scope/units matches, never consent answers. Draft answers need no invented confirmation metadata. `stats STATE --as-of TIMESTAMP --evidence-as-of TIMESTAMP --wait-days 7` separates event and knowledge cutoffs; omitted evidence cutoff uses evidence present in the file. Inventory counts remain current.

## Existing history

The agent maps a supplied list/table/CSV or authorized read-only connector result to minimal rows. There is no built-in Gmail client or arbitrary document parser.

```sh
python3 -B scripts/career_state.py history-preview /chosen/private/workspace/Data/state.json /private/mapped-rows.json
python3 -B scripts/career_state.py history-apply /chosen/private/workspace/Data/state.json /private/reviewed-plan.json --expected-revision 3 --reason "Reviewed original rows and exact-role mappings" --user-confirmed
python3 -B scripts/career_state.py reapply-check /chosen/private/workspace/Data/state.json ROLE_ID
```

Apply the exact preview digest/revision after review. Repeated observations are no-ops. A proposed change to an existing observation's mapping is shown as `mapping_requests` with retained mapping; use a distinct `map_history` reviewed operation. Sparse imports stay observations, not delivery proof. Approximate/unknown dates never acquire invented exact timestamps. No email bodies/credentials are accepted by the import schema.

## Materials and views

```sh
python3 -B scripts/career_materials.py register /chosen/private/workspace/Data/state.json /chosen/private/workspace /private/material-metadata.json --input /private/selected-resume.txt --expected-revision 4
python3 -B scripts/career_materials.py prepare-attempt /chosen/private/workspace/Data/state.json /chosen/private/workspace /private/attempt-request.json --expected-revision 5
python3 -B scripts/career_materials.py verify-attempt /chosen/private/workspace/Data/state.json /chosen/private/workspace ATTEMPT_ID
python3 -B scripts/career_materials.py package-attempt /chosen/private/workspace/Data/state.json /chosen/private/workspace ATTEMPT_ID --slot resume --output /private/selected-packet.zip --as-of 2026-01-15T12:00:00Z
python3 -B scripts/career_snapshot.py export /chosen/private/workspace/Data/state.json /chosen/private/workspace --as-of 2026-01-15T12:00:00Z
python3 -B scripts/career_snapshot.py export /chosen/private/workspace/Data/state.json /chosen/private/workspace --format csv --as-of 2026-01-15T12:00:00Z
python3 -B scripts/career_snapshot.py status /chosen/private/workspace/Data/state.json /chosen/private/workspace
```

Metadata/request formats are in the schema and [state format](../references/state-format.md). Registering stores immutable content once; it does not parse, tailor or create a PDF. Attempt preparation rejects empty material selections, leaving the ID available for a real preparation. Imported/selected slots are validated at schema, runtime and packaging boundaries. Attempt preparation creates identity-checked folders and relative links/reference records. Packaging resolves explicitly selected slots only, never sends, and never overwrites an existing ZIP. References/links fail closed on traversal, escaping symlinks, hash changes or conflicting IDs.

Snapshots use exclusive view locking, source hash/revision checks and previous export fingerprints. A changed/unrecognized workbook is preserved and export returns `written: false`; CLI exits 3 when manual reconciliation is needed. State commits are separate and are not rolled back by a failed export. No macros or executable formulas are emitted. XLSX and CSV use only the standard library. CSV has six preamble/header rows, with the application-table header on row 6, UTF-8 BOM, and formula-like values escaped with an apostrophe. It does not provide a second sheet or formatting; full provenance remains in canonical state. Unsupported formats fail without generating a report. Inspect representative output with an available noninteractive renderer before claiming visual verification; Quick Look thumbnails may crop wide views and do not certify every spreadsheet engine.

## Build an installable local bundle

```sh
python3 -B scripts/build_skill_bundle.py /temporary/output/career-agent
```

This copies only skill instructions/license, explicitly named phase references, fixed helper files, schema and state-format reference; unexpected Markdown is never selected by a wildcard; it excludes candidate data, tests and repository metadata. The output must be absent. BUNDLE.json hashes every included file. The same complete bundle can be installed in a host's supported personal/project skill directory. Source edits are not personal installation, and this project does not install or publish itself automatically.

Optional context enrichment uses context_access and context_insights; omitted fields remain valid in older v1 states and imply no access. Reviewed operations set_context_access (access object) and confirm_context_insight (insight_id, confirmation) require the normal expected revision, user confirmation and reason/history. Exact source scope and purpose gate new insight intake. Suggested insights cannot become confirmed facts; growth-derived facts stay private_interview_only/disclosure=private. Withdrawal marks derived facts context_reuse_blocked and affected historical external artifacts for review. No helper retrieves provider history.

## New saved search cases

The agent uses career_search.py novelty STATE WORKSPACE ROLE.json before quota selection, prepare-case STATE WORKSPACE REQUEST.json --expected-revision N to persist a schema-validated case and Markdown package, and report STATE WORKSPACE BATCH_ID --requested N to verify completion. Exit 3 means quota/presentation is incomplete, not sent. The search_case_request/income_policy schema definitions specify records; no user salary defaults exist. Known JSON/CSV review/index/history tables in Data and explicit registry_paths contribute exact identity evidence. Other tables require host normalization; recognized unreadable/XLSX registry coverage fails closed. Check final output destinations, preserve scoped company/channel exclusions, and distinguish essential unknowns from noncritical wishlist gaps. Draft bodies are Markdown, while a resume_reference may pin an unchanged approved existing version. Persistent partial state survives file/view failures; retry the same immutable request or explicitly reconcile changed content. No research or send code is bundled.

Readiness regressions cover semantic geography matching, scoped management language, ordinary contract clarifications versus legal/user-essential restrictions, absent policy/scope metadata, same-period pay without invented hours, pending consent versus missing factual answers, and unverified employer requirements. No-sends remains operational; helpers never return submission authorization. Inspect source evidence before assigning dimension/applicability/verification: these annotations cannot justify dropping an unrelated hard requirement.

Calendar-pay regressions cover both below-floor cap directions and sufficient/equal monthly/annual controls using twelve months, including unchanged input observations and separate hourly/currency/gross-net mismatches.

## Agent-operated achievement checks

The agent captures verbatim source achievements before rewriting, then uses `career_achievements.py capture|interpret|clarify STATE INPUT --expected-revision N`. `plan STATE INPUT` accepts priority achievement_ids and a small group limit; it suppresses cached answers. `audit STATE AUDIT --draft FINAL.md` checks the actual rendered draft. Inputs follow the schema definitions. These commands are optional agent tools, never end-user steps. Resume registration/search preparation enforce audits when an inventory exists, with existing old-state compatibility; agent instructions require building the inventory on adaptation. Tests exercise actual material/packet writes, ambiguous team numbers, technical before/after units, feature labels, qualitative work, cache reuse, retained secondary strengths and explicit evidence-backed exclusions. Semantic truth and binary extraction remain host/agent review responsibilities.

Search preparation saves incomplete resume text privately rather than discarding it at the audit gate. Revise the documents/audit of a still-preparing case under its existing ID and latest expected revision; optional revision_reason records context. Stable identity/scope hashes, history, immutable old pins and content-bound attempts keep this distinct from a new find or reapplication. Tests include direct and full-packet private-hold disclosure, additional unsupported numbers with confirmed-evidence controls, pending metric meaning, default grouped comparisons and interrupted-case recovery.

## Release maintenance

Maintainers refresh release.json after payload edits with build_skill_bundle.py --write-release --version VERSION --change TEXT (repeat changes as needed), then build an absent bundle directory with --zip /new/path/career-agent.zip. The descriptor hashes payload, not itself or the ZIP, avoiding circular commit/archive hashes. Stable tags and GitHub Releases publish that exact ZIP; never move a published tag or replace its asset silently. Normal users ask the agent to check/update; they do not run these commands. See the bundled updates reference for daily checks, pinned approval, read-only download, compatibility, leases and recovery. No downloaded Python is imported/executed during replacement.

Career extraction is recorded with `career_achievements.py review-sources STATE INPUT --expected-revision N`. It returns current coverage and grouped clarification needs. Adaptation audits include an explicit semantic review; search packet completion checks it even with an empty achievement inventory. These checks validate declared coverage, references and readiness, not the quality of the agent's reading. See [the state contract](../references/state-format.md).

For unreleased payload changes, the published `release.json` is intentionally stale and normal bundle creation refuses it. Run packaging/full-suite checks in a temporary source copy with a descriptor regenerated only in that copy using the existing `--write-release` command (same test version). Do not modify published release metadata or installed copies just to run development tests. Record the code hashes and temporary test log; regenerate actual release metadata only as part of an authorized release.

The optional local HTML portal uses one bundled fixed template and paged JSON data; XLSX/CSV remain supported. It is a generated private snapshot with separately exported browser notes, never a competing campaign database. See [portal workflow](../skills/career-agent/references/portal.md).

Packet work uses prepare-batch for new requests or focused existing-case edits, then deliver for selected current text and requested portal/private archive. The lower-level commands remain available for recovery. Agents prepare inputs; ordinary users do not run scripts. test_consolidated_workflow.py exercises two existing packets after a later achievement/contact clarification and checks actual Markdown, portal downloads, archive bytes and preserved history. Raw conversational inputs are in tests/fixtures/packet-conversation; evaluating models receive only the current user message and attached source files, not expected outputs or this test adapter. Deterministic tests validate helpers; a separate forward run checks agent behavior. For unreleased changes, package tests use a payload-consistent descriptor in an isolated temporary snapshot, without changing the published descriptor.

Final binary review: the agent can run `python3 scripts/check_resume_render.py REVIEWED.md EXPORTED.pdf` (or DOCX). This reads files without modifying state; exit 0 means local text/order retention, 3 means a mismatch, and 2 means inspection unavailable/invalid. PDF requires optional host-provided Poppler; DOCX inspection is standard-library-only. This does not replace visual, hyperlink, source-meaning or employer-form checks.

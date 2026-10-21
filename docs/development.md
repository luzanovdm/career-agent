# Developer and agent operations

Ordinary users install/load the skill, provide documents and converse. They do not run these commands or edit JSON. Agents with authorized shell/file capabilities can use the optional helpers; all helpers use Python 3.10+ standard library, with no network or sending implementation. Keep private records outside the source checkout and installed bundle.

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

`control STATE start|pause|resume --evidence TEXT --user-confirmed` records real research choices; start also requires `--scope`. `research-check STATE` returns 0 when allowed, 3 when disabled, and general errors return 2. The agent checks before every external lookup and propagates pause. No network work is performed by the flag.

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

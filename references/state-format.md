# State format and local helper contract

This is an agent/developer reference. Ordinary users provide information and review changes in chat; they never need to edit JSON or run helpers. Python helpers are optional and contain no network/sending code. [The schema](state.schema.json) is the structural contract; `career_state.py` evaluates its supported subset and adds semantic/reference/time checks. Extra narrative fields are generally permitted; credential/import records deliberately accept only minimal fields.

## Envelope and validation

Version 1 requires `schema_version`, integer `revision` (not boolean), `change_history`, `control`, `profile`, `search_config`, `report_preferences` and every collection below. Record IDs are unique within a collection, nonempty and stable. Reference lists contain existing distinct IDs. Timestamps are ISO 8601 with explicit zone. Duplicate JSON keys, nonfinite numbers and nesting beyond 100 are rejected in every state/record/query loader. Invalid/stale inputs leave state bytes unchanged.

The source format is an initial version, not a migration system. Keep unrecognized/older incompatible imports intact; the agent explains the actual validation error and performs explicit evidence/mapping review rather than pretending they loaded. Validation checks attestations and structure, not factual truth, legal eligibility, actual source access or human permission.

## Record collections

| Collection | Core fields beyond id | Invariant |
| --- | --- | --- |
| sources | kind, locator, coverage, observations | web/document/user_statement; observations have at, evidence, status, primary |
| companies | name, identity, kind, source_ids | company/speculative_prospect; a prospect needs relevance_hypothesis and is not a vacancy |
| opportunities | company_id, title, identity, role_url, kind, source_ids, status_observations | Exact vacancy/contract_project; distinct roles at one employer stay separate |
| facts | statement, status, confidence, context, ownership, disclosure, source_ids, contradiction_ids | Confirmation includes exact evidence, source_id and at; contradictions in either direction block new external claims |
| suggestions | statement, status, source_ids | hypothesis/declined; never a confirmed career fact |
| credentials | kind, title, issuer, subjects, issued_on, expires_on, source_ids, verification, disclosure | Educational evidence only; no identity/document serial fields |
| forms | opportunity_id, status, at, source_ids, fields | observed/provisional; observed requires sources and actual requiredness |
| artifacts | opportunity_id, kind, version, language, path, at, status, fact_ids | Prepared/reviewed version, not a send; optional material_id/material_sha256 pin |
| materials | family_id, version, kind, language, path, sha256, source_ids, visibility, at, fact_ids | Immutable reusable content under Materials/objects; unique family/version |
| application_attempts | opportunity_id, label, at, path, materials | Distinct prepared application instance with immutable material pins; never itself a send |
| attempts | opportunity_id, outcome, at, evidence, channel | Delivery/action record: sent/not_sent/uncertain; optional occurred_at, artifact_id, application_attempt_id, resolves_attempt_id |
| responses | opportunity_id, type, at, evidence | Optional recorded_at; attempt_id identifies exact delivery action; inferred only when unambiguous |
| coverage | opportunity_id, status, channels, checked_at, through | complete/partial/unknown; checked_at can later attest through, which cannot be future to check |
| answers | meaning, scope, units, value, confirmed, valid_from, valid_until, is_consent | Confirmed answers additionally require confirmed_at and confirmation_evidence |
| history_imports | source_locator/kind, employer, role, role_url, date_text/precision, occurred_at, channel, status, event_kind, opportunity_id, evidence_level, provider_message_id/thread_id | Minimal immutable observation; stable fingerprint excludes reviewed role mapping |
| dossier | opportunity_id, statement, classification, at, source_ids | verified/inference/unknown; sources required for verified/inference |
| cases | opportunity_id, prompt, classification, source_ids | hypothetical/publicly_documented; documented requires sources |
| interview_prep | opportunity_id, language, question, outline, question_status, fact_ids, source_ids, pressure_points, employer_questions | Practice hypothesis or attributed public report; candidate claims stay evidence-backed |
| rehearsals | opportunity_id, interview_prep_id, at, language, answer_summary, feedback, next_step, status | practiced/retry_requested/completed; practice does not confirm career facts |
| referrals | company_id, opportunity_id, public_name, observed_role, relevance, relationship, affiliation, verified_at, source_ids | Acquaintance needs relationship_evidence; verified_current needs affiliation_evidence |
| referral_drafts | opportunity_id, referral_id, version, text, professional_reason, fact_ids, source_ids | Exact role match and unique prospect/version; not contact |
| contact_events | opportunity_id, referral_id, status, at, evidence | user_reported_sent/uncertain/reply/declined; no sending implementation |

## Sources, facts and credentials

Source observations use open/closed/unknown/not_applicable and explicit primary boolean. Coverage channels are strings. Exact-role status observations have at/status/source_id; open/closed requires a matching dated primary observation. Unknown remains acceptable without proof. Relevant unofficial/critical public sources remain useful context, with attribution and uncertainty; primary vacancy verification does not suppress them.

URL normalization preserves meaningful query parameters and fragments, including hash-router identities, while removing known tracking queries. It does not guess redirects or mirror equivalence. Reuse a source ID when adding canonical duplicate observations: coverage/observations merge and original locators are retained. Different IDs for the same canonical URL are rejected. Employer requisition identity and exact URL prevent duplicate opportunities; company/title similarity alone does not prove identity.

Fact status is unconfirmed/confirmed/disputed; confidence low/medium/high; context commercial/side_project/volunteer/learning; ownership individual/team/mixed/unknown; disclosure allowed/private/unknown. Exact confirmation needs a source in source_ids. Suggestions require new supporting evidence before a separate fact is confirmed. Both endpoints of declared contradictions are blocked for new external claims. Existing artifacts/materials/outlines/drafts are preserved with review_required and review_fact_ids; a flag is not permission to reuse them. A private artifact uses visibility=private (legacy kind private_fit_assessment is recognized), and may carry confidential evidence_fact_ids/fact_ids. External artifacts cannot embed private evidence references.

Credentials retain only relevant title/issuer/subjects, issue/expiry dates (YYYY-MM-DD or null), sources and disclosure. User-provided educational evidence is not independent verification. Independently_verified requires a primary web verification source plus verified_at. A course/certificate is not commercial experience or automatic mastery. Optional external `credential_claims` references use portrayal earned/current. Current requires known, unexpired dates at use time; unknown expiry cannot be asserted current. Earned may describe a historical credential honestly. Serial numbers/signatures/unrelated identifiers remain only in authorized private originals, preferably redacted, not this metadata.

## Settings, controls and answers

Profile has timeline, selected_directions and metric_dispositions. Timeline retains source, label, context, date precision and optional detailed dates. Metric dispositions are one per fact/question_key: answered/no_metric/unknown/confidential/prefer_not_to_disclose. Ask one compact batch across priority achievements; reopen only for new evidence/requested revision.

Search settings require constraints, salary_floor and salary_goal. Each constraint has meaning, value (null for unknown), hard/preference/negotiable priority and known/unknown status. Money terms are null or amount/currency/gross-net-unknown basis/hour-month-year period. A required employer field does not authorize floor disclosure: use a separately approved desired answer with units. Report preferences have frequency and results_only; they do not schedule work.

Control starts unauthorized/paused with empty scope/history. Replay ordered start/pause/resume decisions, including evidence, at and scope, to validate current flags. A new start sets scope; pause/resume preserve it, and resume requires an earlier start. Imported flags cannot override pause or authorize research. Every external worker checks control before a new lookup.

Answer keys use one canonical, type-aware representation of meaning/scope/units: true differs from 1. Lookup requires exact key, confirmed=true and validity `[valid_from, valid_until)`. Only confirmed intervals participate in overlap rejection. Draft answers may omit confirmation metadata and are never reused. Confirm through a reviewed transition. Compensation units include currency/basis/period. Consent namespaces privacy./consent./agreement. require is_consent=true and exact company/opportunity/text-version/purpose scope; lookup never reuses consent answers at all.

## Reviewed changes and historical import

Append events, facts, materials and sources through validated transactions. Full-section settings replacements require expected revision and a reason. Narrow reviewed operations are confirm_fact, confirm_answer, supersede_answer, observe_opportunity, resolve_contradiction and map_history. They preserve before/after/request, reason, time and revision_from in change_history. Facts keep their exact statement/ID during confirmation. Superseding answers get a new ID and close the prior interval. Arbitrary patches are unsupported. Expected revisions reject stale previews instead of overwriting concurrent work.

History preview receives agent-normalized rows from supplied text/table/file or scoped authorized mail results. It shows original source and exact/unknown mapping, date precision, status, new observation count and warnings. Approximate/unknown dates cannot become exact occurred_at. Provider-observed mail needs message provenance; user lists remain user_reported and cannot claim provider delivery. Full bodies/credentials are not accepted. Threads, follow-ups and unscoped company contacts are not application counts.

History fingerprints use normalized observation fields; opportunity mapping is separately reviewable. Repeated imports are no-ops. If an existing observation has a proposed mapping change, preview retains its stored mapping and lists a mapping_requests entry requiring an explicit audited map_history operation. Apply uses the exact digest/revision and never silently substitutes a mapping. Status differences and stronger action evidence remain preserved. Before any repeat preparation, reapply-check surfaces exact-role history and possible unresolved identity matches; this does not authorize sending.

## Material and attempt layout

A material record pins a central relative path, SHA-256, version and evidence/disclosure. The material helper stores selected content once, under its hash, and never creates PDFs automatically. Prepared application attempts require at least one selected material; keep a pre-selection draft in conversation rather than freezing an empty immutable attempt. Slot names must match lowercase `[a-z][a-z0-9-]{0,39}` in imported state, runtime verification and packaging, and package members are flat safe filenames. Application-attempt pins have slot, material_id, sha256, version, link_path, reference_path and symlink/reference link_mode. Relative paths must stay in the selected workspace and the exact attempt directory. Every company/vacancy/attempt directory has a readable slug, stable-ID digest and identity marker. A later attempt cannot overwrite earlier pins, letters, form answers, evidence or correspondence. Shared vacancy Research is separate.

Relative symlinks and version/hash reference records survive moving the whole workspace. Unsupported symlinks use reference files with no silent binary copy. Verify hashes before use. Explicit selected-slot packaging rejects private/flagged materials, escaping links and current-credential claims that are no longer valid, and includes only selected files plus a minimal manifest. It never sends/uploads or exports the entire library.

## Event time and reporting

For a delivery record, `at` is recording/reconciliation time. `occurred_at` optionally specifies actual action time, defaulting to at for an original action. A sent/not_sent reconciliation references an uncertain action and inherits its original occurrence; it is not a new send. It preserves history and accepts receipts after the original action but before reconciliation was recorded. Responses have event at and optional later recorded_at; associate them with the exact send attempt. A new action while an uncertain submit is unresolved is rejected.

Response types are auto_receipt/human_reply/interview/offer/rejection/bounce/withdrawal/rejected_before_application. All except the last require a prior actual send for the exact role; pre-application rejection requires no prior send at its event time. Receipt is not hiring progress; bounce is not employer rejection. An old bounce stays in historical counts but only the latest relevant delivery attempt can be a current delivery problem. Unresolved submits cannot be classified as silence.

Statistics state both event/report cutoff and evidence cutoff. Omitted evidence cutoff means evidence present in the file; specify it to reproduce an earlier knowledge snapshot. Later checks may attest complete historical coverage through the event cutoff; unknown/partial coverage cannot. Waiting windows use actual send occurrence. Inventory/import counts remain current, not historical snapshots. Unique confirmed-sent roles are denominators, never packet versions or message threads. Zero denominator is unavailable; categories can overlap.

## Local safety and view contract

Transactions lock, validate, check expected revision where applicable, create protected Backups/State copies and atomically replace canonical state. No-op operations leave bytes/revision unchanged. Do not automatically remove stale locks or arbitrary orphan files; inspect/reconcile. File permissions are not encryption, and network/synchronized filesystems are not supported coordination guarantees.

Career.xlsx has exactly Applications and Metadata sheets. Career.csv is a plain application table with snapshot markers and state hash above its header; canonical state retains full provenance. CSV formula-like values are escaped as text. Tracking reports support only XLSX and CSV. All values are literal escaped text, XML-forbidden characters are handled, and links are limited to intended HTTP(S)/private material paths. Revision/hash/export time visibly marks the snapshot; fingerprints detect stale or manually edited views. Preserve changed/unrecognized views and reconcile through conversation. View failure never rolls back valid state or labels an old workbook current. No two-way workbook sync, provider client, send path, generic document parser or background scheduler is implemented.

See source `docs/development.md` for agent-operated CLI examples, and the copyable skill references for user-facing workflow rules.

Optional context enrichment uses context_access and context_insights; omitted fields remain valid in older v1 states and imply no access. Reviewed operations set_context_access (access object) and confirm_context_insight (insight_id, confirmation) require the normal expected revision, user confirmation and reason/history. Exact source scope and purpose gate new insight intake. Suggested insights cannot become confirmed facts; growth-derived facts stay private_interview_only/disclosure=private. Withdrawal marks derived facts context_reuse_blocked and affected historical external artifacts for review. No helper retrieves provider history.

## Saved search cases

Optional search_cases preserves batch ID, exact opportunity, form/attempt references, initial novelty evidence and registry fingerprints/errors, compensation observations/estimates, typed condition assessments and preparing/saved phase. Legacy states may omit it. income_policy records confirmed floor/goal dispositions, units through salary records, work hours/employment and selected case types; optional excluded_companies persists exact names/identities/domains. Unpublished pay is accepted unless the user explicitly excludes it; sourced estimates never become employer commitments. company_outreach is a distinct opportunity kind with a sourced need/contact route and unknown vacancy status, not an invented opening. Statistics separate advertised opportunities and company outreach cases; total opportunities represents actionable cases. career_search.py verifies actual material files/readback/current view and computes the new-case quota separately from general prepared counts. No stored readiness flag overrides unresolved requirements.

Draft-readiness evaluation distinguishes job constraints from user context/operational controls. Optional condition dimension/covers/applicability/verification metadata connects semantically equivalent evidence without discarding unknown custom hard constraints. role_track/management_role scopes leadership criteria. income_policy may omit weekly_hours/case_types/employment metadata or be absent/null; omission is not confirmation or exclusion. Fixed same-period salary comparison needs no weekly-hours default. Draft-ready and pending-consent/submission authorization are separate results; no send path is implemented.

Compatible fixed monthly/annual compensation uses exact twelve-month normalization for floor/cap/goal comparisons, retaining source units and observations. No hourly, currency or gross/net conversion is inferred.

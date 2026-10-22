# Portable records, storage and handoff

Private records belong to the user. Offer a friendly workspace choice such as Documents/Career Agent and reuse the confirmed location; no path is silently selected. Separate named workspaces prevent profile/cache mixing. Originals remain unchanged or referenced where the user keeps them. Profile.md is a readable view; structured state owns facts/events. Materials stores reusable immutable versions once. Applications uses the [company/vacancy/attempt layout](materials.md). Generated Career.xlsx (Applications/Metadata), or plain Career.csv, is an inspection snapshot with state revision/hash, event/evidence cutoffs and export date. CSV carries generation markers/state hash above its table header, without formatting or a second sheet; full provenance stays in canonical state. If files cannot be authored, use explicit text/table handoff and do not claim a saved report. Backups protects previous state/views; no author server or encryption guarantee exists.

A complete private handoff/export includes:

- Active workspace/profile, schema/state revision, last successful view revision/hash and stale/export-error status.
- Source inventory/locators, timeline, confirmed/unconfirmed/disputed facts, hypotheses, bidirectional contradictions, ownership/disclosure, credential evidence and verification/expiry, selected directions and metric dispositions.
- Independently classified search constraints, unknowns, approved salary-answer units, private floor and answer-cache scopes/validity/confirmation. Never send the private floor as a required-field default.
- Explicit research scope/start/pause decisions with provenance, report frequency and results-only preference.
- Company prospects, exact opportunities, canonical/original URLs, dated observations and source coverage.
- Reusable material version IDs/hashes, relative paths/references, exact attempt pins, letters/form inventories and packet versions. Export selected artifact binaries only when requested, not the entire library.
- Imported history observations, original source/provider message/thread IDs, approximate dates, unresolved identities/status differences and reviewed mappings; action/reconciliation times, response-to-attempt links and coverage cutoffs.
- Interview mode (materials only by default, explanation on demand or explicitly chosen interactive practice), scope/decision provenance, saved-material paths or unsaved handoff status; dossier claims and sources, verified/inference/unknown classifications, question hypotheses, supported answer outlines, pressure points, employer questions, hypothetical/documented cases, rehearsal summaries/feedback/progress and day-of logistics/unknowns.
- Referral prospects, current-affiliation sources/dates, relationship evidence, versioned drafts and separately authorized/user-reported contact events. A draft never means contact occurred.

With no private files/shell, maintain the same useful records as small tables or structured text, offer explicit export and request import in a new session. Do not claim a text block was saved or that a chat remembers files forever. Export sensitive source content only when requested; the user's AI host/providers process what they share.

In a complete local bundle, helpers are under scripts/ and use references/state.schema.json and state-format.md within the same skill folder. When these optional helpers are available, the agent operates them: state validation, strict JSON, reviewed expected-revision changes with reason/history/backups, history preview/import, exact answer lookup, material pinning and deterministic statistics. A standalone installed skill does not depend on the source helper or a proprietary tool. Native file-capable hosts should preserve these invariants through available capabilities without requiring the ordinary user to edit JSON or run commands.

Before refreshing views, compare the previous export fingerprint. Preserve an externally edited view and reconcile in conversation; it is not an authoritative send record. If export fails, retain valid state and say the view is stale/not refreshed. To relocate or switch profiles, confirm the active destination, preserve the old copy, validate state and relative links, and never merge another person's answers implicitly. There is no background scheduler or multi-device synchronization service.

Include context-access decision/scope/purposes/history and insight provenance, inference/confidence/confirmation in private handoff. Withdrawal blocks future reuse and flags affected external drafts; it does not delete provider history. Exclude private growth from employer-facing exports.

Optional planning records in the private profile/handoff include calendar opt-in/source scope, confirmed timezone/work hours and user-chosen load limits, unknown/fresh/stale availability with checked_at/coverage, proposed slots/buffers and actual successful scheduler IDs. Store minimal planning metadata, not unrelated event contents. Preserve next steps independently of chat memory; never imply the generic ledger itself supplies connectors/background monitoring.

Include search-case batch IDs, initial novelty evidence/registry hashes and coverage errors, compensation provenance, condition assessments, exact form and attempt references, preparation phase and current-view verification. Keep company outreach distinct from advertised vacancies.

Include the verbatim achievement inventory, source metric spans/units/attribution, versioned meaning interpretations, grouped clarification dispositions and per-target adaptation audits in private handoffs. They stay separate from external document text; historical versions remain immutable. See [achievement adaptation](achievement-adaptation.md).

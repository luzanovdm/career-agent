# Career Agent UI interaction revision

This refinement preserves the incumbent interface and extends its shared-control coverage. The documented artifact is immutable `review-candidate-kit4/`; existing owner previews were left untouched. Development screenshots must identify the exact UI bundle, actual backend checkpoint, and isolated fictional workspace. Final written kit4 review and backend full-release acceptance are separate gates.

## Main jobs

- Understand the next work across career tracks without confusing preparation, delivery, referral, and hiring facts.
- Open a case, read its context, edit its exact selected materials or private notes, and save with clear revision feedback.
- Hand complex work to the conversational agent with a precise editable prompt. Copying does not execute the intent or grant new permission.

## Composition

Retain system fonts, blue emphasis, compact borders, quiet surfaces, and the familiar sidebar. The case overview leads with track/search filters, derived work columns, and a Board/Table control. Card content is reduced to company, role or need, tracks, contact, next step, and the leading blocker; identifiers remain available without dominating the card.

Case detail leads with company, role, contact, next step, and one clear agent handoff. Materials, interview preparation, and history are distinct views. The document selector uses human labels and starts with the message or resume, rather than the private dossier merely because it sorts first. Private notes remain visible and editable at narrow widths. Long immutable IDs and hashes belong in disclosure details.

Simple profile/contact/note/theme edits save directly. Preparation, rewriting, review, research, and reconciliation open an accessible prompt dialog with the intended outcome, exact workspace/case/packet/version scope, editable text, Copy, and a selectable fallback. The dialog never reports work as started.

## Language

Interface locale is chosen during bootstrap and saved canonically. Built-in English/Russian catalogs each contain 332 matching stable keys and use text-only interpolation, locale plurals, and Intl date/number formatting. Generated locales live in workspace customization outside the signed release. Candidate content and document language remain unchanged. Runtime issues are translated by stable codes.

## Integrity and verification

Save/Cancel, retained drafts, explicit comparison/rebase on conflicts, partial receipts, lost-response lookup, safe artifact links, SSE/replay/polling, and bounded pagination remain required. Test initial loading, empty/failed/dirty/conflict states, keyboard focus/return, 200% zoom, forced colors, reduced motion, and both locales. Measure actual production assets and cold/warm UI/API timings before performance claims.

## Independent review repairs

The shared styled React Aria layer now covers every authored interactive control, including board collections, required single-select stage navigation, checkboxes, tooltips, links, disclosures and dialogs. Static content and announcements stay semantic. Detail owns heading focus on first mount by case identity; transaction refreshes retain edit focus. Pristine editing always offers Cancel while no save is pending. A global handoff passes the active board track filter to the typed API and validates the returned exact subset; readable direction names come from that descriptor. Copying remains inert. See UI-KIT-AUDIT.md and the final candidate evidence for review status.

## Incumbent visual contract

The approved task-6 design specifies the calm system-font sidebar, blue emphasis, compact lists, and material editor/private-notes composition. The current `src/styles/system.css` and `src/ui/controls.tsx` retain those choices. This is a control-coverage refinement, with no replacement visual world or new font/theme framework.

| Observed source choice | Current implementation and purpose |
| --- | --- |
| System typography | `-apple-system, BlinkMacSystemFont, "Helvetica Neue", "Segoe UI", sans-serif`; 14px body with 1.5 leading; 28px primary heading; 13px control text. No downloaded font. |
| Semantic color roles | Light canvas `#fff`, text `#202024`, accent/focus `#0068d4`; dark canvas `#1c1c1e`, text `#f5f5f7`, accent `#8ac3ff`, focus `#99ceff`. System mode resolves the same dark roles from OS preference. |
| Compact shared controls | Regular/small buttons have 34px/28px minimum heights; fields use 36px; control radius is 6px, surface radius 8px, and visible focus is 3px with 3px offset. |
| Quiet hierarchy | A 208px desktop sidebar, restrained borders and tonal wells organize work. Shadows are limited to tooltip/popover surfaces; they do not turn every case into a raised panel. |
| Responsive composition | The shell and detail layouts collapse at their existing breakpoints; stage navigation and bounded board columns reorganize, with a selected-stage view at narrow widths. Private notes and readable documents remain available. |
| Behavioral ownership | Shared styled Button, Field, Choice, Check, Link, Disclosure, Hint, DialogSurface, and exported collection/tab primitives use React Aria behavior. Static prose, quotes, headings, and announcements retain semantic HTML. |

CSS tokens remain the implementation source of truth. This table records the inspected implementation against the incumbent design; it introduces no new tokens or claim of a new visual inspection. The external approved DESIGN.md remains unchanged.

## Acceptance scope

The API and SQLite ledger own business state, selected immutable materials, allowed actions, and derived stages. Browser snapshots and unsaved fields are memory-only. Complex prompt handoffs are editable and inert: opening or copying one neither executes work nor grants research permission. There is no hosted service or sending path.

The kit2 independent review passed authored-control coverage and the targeted P0/P1 repairs. The final independent kit4 UI verdict passed. The verification scope is recorded in VERIFICATION.md. Backend clean-workspace acceptance applies to the final 1.0 archive; screenshot provenance remains CP2 development and does not establish backend readiness.

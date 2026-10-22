# Preserve meaning when adapting achievements

Read this before extracting achievements or adapting a resume. The agent performs the steps and optional helper calls; users supply documents and answer small native questionnaires, never scripts or JSON.

## Capture before rewriting

Preserve each original achievement verbatim, including every number, unit, comparison, qualifier, attribution and source locator (document version/page/section). A source claim is evidence of what the resume says, not automatic proof of its interpretation. Keep contradictory versions, commercial versus side-project context, and personal versus team scope. Do not overwrite the original with a polished paraphrase. Capture qualitative achievements too. A feature name plus “owned” is a starting clue, not an accomplishment ready for reuse.

Use an achievement evidence record linked to its source fact. The optional helper captures lexical numerical anchors. With multiple unmapped numbers it retains the complete original span as one group, preserving numerical order and comparisons; the agent can supply more precise grouped spans from the source. A single unmapped number remains an uninterpreted anchor. The agent must read the source to identify the complete measurement span, units and attribution; lexical extraction is not a measurement parser. Do not silently drop numbers because they are ambiguous or reinterpret a team saving as the candidate's personal saving.

## Understand, then select

For priority achievements relevant to a selected direction or target, record a separate versioned interpretation:

| Field | Establish from evidence |
| --- | --- |
| Problem | User workflow, technical constraint or concrete need |
| Scope | System, component, audience or boundary; no invented scale |
| Decisions | Mechanism, trade-offs or choices actually made |
| Contribution | What the candidate implemented, decided, coordinated or contributed |
| Outcome | Supported change, delivered capability or qualitative result |
| Metric context | Meaning/units, baseline and result, period, evidence, team versus personal attribution, disclosure |

Each field has `supported`, `hypothesis`, `unknown` or `confidential` status and supporting fact IDs. Reuse clear source evidence and confirmed answers. Missing one field does not invalidate the achievement: contribution plus meaningful supported problem/scope/decision/outcome can produce strong qualitative writing without a number. Do not invent business significance, personal motivations or causal impact to fill a template. “Owned the selector” becomes useful only after understanding the workflow, technical responsibility or outcome; merely adding “critical”, “strategic” or “drove growth” is not a repair.

Ask only material unresolved questions in **one compact grouped batch across priority achievements**, through an applicable native form. Offer editable interpretations based on actual evidence, clearly marked as hypotheses. For example: “Does this describe implementing the mechanism, making the design decisions, or contributing to the team's result?” Never suggest invented numeric anchors. Group metric meaning, units, before/after, period, evidence, contribution and disclosure together. Allow unknown, no metric, confidential and prefer not to disclose. Record an outstanding question as `pending`; record the actual answer/disposition once. Reuse it, including unknown/confidential; reopen only for new evidence or a requested revision with a reason. Do not ask every accomplishment the same questionnaire or force irrelevant detail into a resume.

## Private selection and loss audit

Before saving/reusing a role-specific resume, compare the **actual final draft** with the complete source achievement inventory, not just a template or the last CV version. Store a private adaptation audit with target role, date and one decision per source achievement and source metric:

- `include` / `qualify`: exact rendered span, supported fact IDs and interpreted meaning fields. Preserve numerical values, units and before/after direction, with the known outcome scope. A team or system result can be retained with honest scoped wording plus the candidate's supported contribution. Do not claim personal causality unless confirmed.
- `omit_irrelevant`: explain why this evidence does not serve the particular target, with concrete role-relevance evidence. An intentionally irrelevant omission is valid; “unclear context” or “numbers are risky” is not relevance evidence. An individually irrelevant metric may be omitted while retaining the useful qualitative achievement, but needs its own specific target-relevance evidence; missing context is not that evidence. Otherwise clarify, qualify or keep it privately pending.
- `preserve_pending`: original remains intact in the fact/evidence library, with a grouped clarification/disposition; no unsupported external claim. If part is clear, capture it as a separately supported qualitative achievement rather than laundering an unresolved number into vague impact.
- Metric `private_hold`: retain the source number privately under recorded confidential/prefer-not-to-disclose disposition; use only supported permitted wording externally. Never copy the private audit or hidden context into a recruiter deliverable.

Review important strengths across versions: an adapted CV must not silently lose a significant measurement, technical decision or contribution simply because its meaning was incompletely expressed in the original. Show concise unresolved context in the private handoff, without belittling the applicant in external text. Important is relevance-based, not “every original bullet in every CV”. Audit omissions as well as additions. Audit the cover letter against the same facts when it reuses an achievement.

The helper checks source coverage, referenced facts, exact draft spans, number/unit retention and scope annotations; it cannot prove that prose accurately represents the cited evidence. Read the original, interpretation and rendered wording together, including comparison direction and causality. It deliberately does not infer numeric conversions or silently substitute equivalent units. If a legitimate reformulation needs different numerical representation, preserve the original and its supported conversion rationale for explicit review rather than bypassing the audit.

## Optional local records

See the bundled `references/state-format.md` for `achievement_evidence`, `achievement_interpretations`, clarification dispositions and `adaptation_audit`. Agent-operated `career_achievements.py` supports capture, interpret, clarify, plan and audit with strict loading and normal revision/backup protection. Never manufacture confirmation metadata. Old states remain readable; on the first new adaptation, build the inventory from available source versions before drafting. An empty inventory is not a reason for the agent to skip this workflow.

Incomplete drafts remain saveable as private materials without a completed audit; do not make missing context a barrier to preserving work. New external resume registrations with an inventory require a structurally valid audit against the actual text. A saved draft with preserved pending achievements, unknown measurement context or an explicitly pending metric-context answer remains conditional for review, never a completed/ready claim. Check held/omitted numbers against the actual rendered achievement and account for every additional numerical claim with separately confirmed evidence. A declaration of private hold does not make a visible number private. Confidential metric holds are recorded disclosure choices, not repeated questions. For a search packet, set audit `target_role` to its exact opportunity ID. Search packets carry the audit into immutable resume metadata and verify it on readback. Reusing an unchanged resume needs a per-target review bound to its exact hash; Markdown uses actual bytes. Binary resumes require host-readable extracted text bound to that hash: this helper does not parse PDFs/DOCX and cannot verify the host's extraction. Historical materials remain immutable and are not rewritten when an inventory is added. If current evidence makes reuse incomplete, keep the historical version and produce/review a new version or explicitly update the private selection audit, never silently mark it ready.

An incomplete search packet keeps its actual Markdown in the private material library, with review errors and original novelty retained. Revise documents/audits under the same still-preparing case ID with the current expected revision; record a reason when useful. Identity, scope and prior versions remain fixed. This is preparation recovery, never a new opportunity or permission to resubmit. Complete packets and reported sent/uncertain attempts cannot be revised through this path.

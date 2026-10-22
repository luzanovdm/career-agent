# Profile and adaptive intake

Use [the interaction contract](interaction.md) for every intake choice, factual clarification or preference: native questionnaires are required when applicable in the current host/mode; keep conclusions in chat and avoid duplicate prose questions.
## Begin from evidence

In the first onboarding invitation, explicitly ask for current and available older or role-specific resume versions, together with a concise optional supporting-evidence list. Do not ask only for the current resume or rely on the user to volunteer historical versions. Acknowledge files already supplied instead of re-requesting them. Missing old files never block progress. Offer a short context-relevant optional checklist: diplomas/degrees or transcripts where relevant, professional certificates, course records, portfolio/GitHub and side-project descriptions, publications, recommendations, and other evidence of skills. Let the user skip any item; never demand everything. Prefer redacted copies when documents contain identity numbers, serials, signatures or unrelated personal details. Ask the user to share documents through the host's supported file/text mechanism; do not assume file access or fetch private profiles without consent. Start with one available document if that is all they have.

Extract a timeline with dates and precision (month/year/unknown), employer or project, title as stated, employment type, technologies, scope, outcomes and source locations (document/version/page or section). Keep commercial employment distinct from side projects, volunteer work and learning. Distinguish “I implemented”, “I led”, “I contributed” and “the team achieved”. Do not double-count overlapping periods as years of experience. Retain contradictions, confidence and provenance; present a short discrepancy choice instead of silently choosing the stronger claim.

Store a fact bank separate from hypotheses. For each fact: ID, supported statement, source IDs and locators, confidence, contradiction IDs, commercial/side-project context, individual/team ownership, disclosure permission, and confirmation evidence. A suggestion never becomes a confirmed fact merely because it appears in a draft. Confirm only the exact wording the user verifies, with evidence (a user statement can itself be a source). Keep confidential evidence private.

## Credentials and other supporting evidence

Extract only relevant credential title, issuer, subject/skills, issue and expiry dates, source and disclosure choice. Distinguish user-provided documents from independently verified credentials; a supplied certificate is not independent verification. Store document originals privately only when authorized, or keep references to user-managed originals. Do not copy identity/document numbers, signatures or unrelated personal data into the fact bank, resumes, public metadata or generated views.

A degree, course or certificate is educational evidence. It is not commercial experience, mastery, seniority or automatic qualification. Keep learning separate from employment. Do not describe expired credentials as current; unknown expiry stays unknown. Preserve historical earned credentials accurately when relevant, and check current status when a role requires an active license. Publications and recommendations also need source/context and do not prove every implied skill or endorsement.

## Propose direction portraits

Present short portraits based on supported facts, with relevant evidence and remaining questions:

- Direct stack and demonstrated level.
- Adjacent stack with transferable concepts and real gaps.
- Growth in responsibility, technical leadership or people leadership, distinguishing aspiration from experience.
- Product/startup/side-project work, separating shipped products from experiments.
- Optional contract/short-project lane if useful for temporary income or flexible work.

For each show likely work, supporting facts, stretch points and what to validate. Ask the user to choose, edit or decline lanes; record selected directions separately from qualification assessments. Do not start research yet.

## Guided confirmation

Check for material missing/conflicting dates and transitions, omitted technologies or achievements, unclear personal ownership and thin supporting evidence. Ask only when the answer changes a selected direction or an impending action. Offer prefilled alternatives, allow unknown/confidential/prefer not to disclose, and never demand sensitive reasons for a career gap or block useful work over a nonessential omission. Use short adaptive batches based on the documents. For example, if an API project is documented, offer: “Implemented [supported API component] for [known workflow]”; “Owned [confirm scope]”; “Contributed [known component] to the team's [supported outcome]”. Brackets are questions, never facts. Suggest technologies only when context makes them plausible and explicitly label them hypotheses. Let the user select, edit, complete, reject or say unknown.

Across the priority achievements, ask one compact clarification batch, selecting only missing items that matter: baseline/result and units, measurement period, evidence, team outcome versus personal contribution, and permission to disclose. Persist the answer or disposition: `answered`, `no_metric`, `unknown`, `confidential`, or `prefer_not_to_disclose`. Do not repeat this batch separately for every accomplishment. Do not repeatedly ask the same metric question; reopen only if the user supplies new evidence or requests revision. An unquantified accomplishment can still be strong: action + system/problem + supported scope/outcome. Never manufacture a percentage, causal attribution or seniority label.

Example with synthetic evidence: “Implemented retry handling for Northstar Demo's invoice importer; the team reported fewer manual retries.” Use the team result only if supported and disclosure is permitted. Without outcome evidence, use “Implemented retry handling for the invoice importer.” Do not invent an improvement rate.

## Separate search configuration

Capture incrementally after direction selection. Every entry has a value, `hard`/`preference`/`negotiable` classification, known/unknown status, confirmation date and optional validity period:

- Geography; work authorization only where needed; working and interview languages.
- Relocation, remote/hybrid/on-site and time-zone overlap.
- Company jurisdiction and acceptable payout methods/countries, never account identifiers.
- Domain exclusions; product/outsource/outstaff preferences.
- Employment/contract type, weekly hours, availability.
- Salary floor and goal separately: amount, currency, gross/net, hourly/monthly/annual period and working-hours basis where relevant. Do not compare amounts with mismatched units or guess exchange rates.
- Optional temporary-income target, deadline and contract/short-project scope.

Before search, reuse current confirmed income/hours/employment preferences and ask only material missing ones through a native form. Preserve explicit company exclusions. Undisclosed pay is acceptable; use sourced comparable company/market evidence in the actual hiring geography, label estimates and unknowns, and never invent an employer promise. Unknown is neither pass nor fail. Clarify essential unknowns before an action depending on them. Keep private salary floors out of external materials. A required field does not authorize disclosure of the floor: ask for or reuse the user-approved desired answer, with currency, gross/net and period. End by asking whether the user wants to start discovery, refine the profile or pause.

Offer to import existing application history from a list/table/file using [history import](history-import.md). Connecting mail is optional and separate from profile intake.

Offer optional [scoped other-chat/memory enrichment](context-enrichment.md) once without blocking intake; skip is a complete answer. Keep suggested strengths separate from verified career facts and all growth areas private for interview preparation.

Preserve exclusions at their confirmed scope: company-wide exclusions persist across sources; a restriction on a sending channel does not automatically ban discovering public evidence through that channel. Never turn one user's channel choice into a universal default.

# Career Agent

A career assistant you use through conversation: review your experience, choose career directions, find roles and companies, prepare applications, track progress, and practice interviews. It keeps claims grounded in evidence and writes confidently without inventing achievements. When adapting a resume, it preserves the original achievements and numbers, clarifies their meaning in small batches, and checks the draft for unexplained losses.

## Start with a conversation

1. **Load or activate the skill in your agent.** Use your host's supported skill installation/loading feature with the [complete release bundle](https://github.com/luzanovdm/career-agent/releases/latest/download/career-agent.zip). An instructions-only source-folder copy lacks bundled helper execution and release identity; choose the complete bundle for update support. In Codex or Claude Code, invoke `career-agent` through the host's skill command or picker after installation. Merely viewing a Markdown file does not activate a skill in every app. [Host-specific notes](docs/compatibility.md) explain the supported options.
2. **Say what you need.** For example: “Help me set up my profile from my resume versions. Ask guided questions and wait before starting research.” You can also start with a selected vacancy, interview invitation or existing application history.
3. **Upload or paste what you have.** Start with any available resume version. Older versions, relevant diplomas/certificates/courses, portfolio/GitHub, publications, recommendations and side projects are optional; a short checklist lets you skip or provide redacted copies. Missing files do not block useful work. If your host cannot read an attachment, the agent asks for readable pasted text.
4. **Choose from short, useful suggestions.** The agent presents intake choices, clarifications and preferences in your host's native questionnaire when it supports one, with evidence-informed directions and ready-made answer choices plus free-text correction. Findings and explanations stay in chat. If this host/mode lacks an applicable questionnaire, it uses a short numbered text fallback without requiring a mode switch. You can edit them or say unknown, confidential or prefer not to disclose. It gathers the remaining important questions in compact batches.
5. **Review and continue in chat.** Ask to start or pause research, prepare a particular role, import prior applications, practice an interview, or show progress. The agent operates available local utilities itself. You do not need to run scripts or edit JSON.

Conversation and intake follow your language. Resume, cover-letter and interview language are separate choices for each role. Everything distributed in this source project is English.

Optional enrichment from selected accessible chats/memory can help identify strengths and private interview preparation needs. The agent asks once; skipping is fine. Access is limited to your chosen sources, suggestions require confirmation, and private growth areas never go into application materials. Native questions, previews, planning, connected files/mail/calendar and reminders are used only when supported and appropriately authorized; installation does not enable background monitoring.

## Where your information lives

When your host can write local files, the agent asks you to choose a friendly private location, such as **Documents/Career Agent**. It reuses the chosen workspace and keeps it outside the source repository and installed skill. It does not create a real candidate workspace merely because this project was downloaded.

| In your private workspace | What it contains |
| --- | --- |
| `Profile.md` | Readable career profile, directions, supported achievements and important unknowns |
| `Originals/` | Immutable resume/source copies you authorize, or references to originals you keep elsewhere |
| `Materials/` | Shared immutable resume/material versions, stored once with hashes |
| `Applications/` | Company → exact vacancy → distinct attempt, with pinned relative material links/references, letters, form answers and evidence |
| `Data/state.json` | Structured facts, constraints, source evidence, application history, attempts, responses and progress |
| `Career.xlsx` | Generated view with **Applications** and **Metadata** sheets: readable rows, links, filters, frozen header and revision/export markers |
| `Backups/` | Protected local state backups and retained prior generated views |

Unchanged resumes are reused through relative symlinks or portable reference files; the agent does not create another PDF for every application. Tailored content gets a distinct version, and earlier sent attempts retain their exact version/hash.

The structured state is authoritative. The workbook is for inspection; ask the agent for changes. It checks the previous export fingerprint and preserves a manually edited workbook before any refresh decision. It does not silently treat spreadsheet edits as applications you sent. If an export fails, valid state stays saved and the agent says the view was not refreshed. Spreadsheet tracking reports use XLSX or CSV; the optional fixed HTML portal is a separate local view. CSV provides a plain application table with generation markers above its header; full provenance stays in canonical state. If your host cannot create either file, the agent offers a text/table handoff and clearly states that no spreadsheet was saved.

There is no author-operated server, hosted database or telemetry. Your chosen AI host and connected providers still receive data you use through them. Local files have no encryption guarantee. In plain chat without private file access, the agent works with conversation records and offers explicit export/import; it does not promise automatic persistence. [Storage details](docs/storage.md) explain profile switching and view freshness.

## Bring your existing history

Paste a list, upload a table/CSV/file, or provide what you remember. Sparse entries and approximate dates are welcome. The agent previews employer/role mappings, preserves uncertainty and reconciles duplicates without overwriting stronger evidence. A company contact does not mark every role at that company as applied. Prior sent, uncertain or bounced applications trigger a review before reapplying.

If an authorized Gmail or compatible mail connector is already available, the agent can offer a scoped **read-only** check of Sent and replies. Connection is optional. A thread is not automatically an application, and a user list is not proof of provider delivery. Import never sends mail, marks it read or starts research.

## Research and preparation

“Find suitable opportunities” produces new saved application cases with ready-to-review Markdown packets, not just links. Known exact roles remain revisits. Draft resumes, covers, dossiers and form answers are .md; identical approved material versions are reused. PDF/DOCX conversion waits for a required upload or your explicit request. Undisclosed salary is acceptable with transparent company/market estimates or unknowns; your private floor is used internally. See [search completion](skills/career-agent/references/search-cases.md).

Discovery covers job boards, freelance markets and companies found through product needs, engineering blogs, repositories and technology ecosystems. A company prospect without a verified opening stays separate from a vacancy. Research begins only when you choose; pause stops new lookups.

When available and authorized, local rdrr can extract public pages discovered through the host's search tools. It is optional, does not replace search, and cannot guarantee access to dynamic, PDF or protected content. Friends do not need an author account or service, and the skill never silently installs software. [Research-tool guidance](skills/career-agent/references/research-tools.md) explains fallbacks.

Application and referral drafts never authorize sending, creating accounts or accepting agreements. The agent keeps private fit assessments separate from external claims, and a required salary field does not authorize disclosure of your private floor. Interview preparation can start from an invitation, readable role description and available profile; you do not need to finish every earlier phase first.

## For contributors

This is a portable [Agent Skill](skills/career-agent/SKILL.md) plus optional, standard-library Python utilities. It has no automatic sending, scheduler, inbox integration or document parser of its own. Hosts provide the capabilities they actually support. See [architecture](docs/architecture.md), [developer operations and tests](docs/development.md), [state format](references/state-format.md), [project instructions](AGENTS.md) and the [MIT license](LICENSE).

## Updates

A versioned bundle checks the public GitHub release descriptor on invocation when networking is available, using a 24-hour cache. Ask “Check career-agent updates” for a fresh check. A newer release offers Update/Later; installation changes require your approval and an idle workflow. Local edits are preserved, backups support interrupted-update recovery, and private career files are never migrated by the updater. Offline checks leave normal use available and do not claim the installed version is latest. This is on-invocation checking, not background monitoring.

Older unversioned installations need one ordinary bootstrap update. A read-only host can download the complete versioned ZIP; an uploaded ChatGPT bundle requires explicit replacement/reloading through its supported surface. No platform auto-update behavior is assumed. See [release notes](CHANGELOG.md) and [maintenance details](skills/career-agent/references/updates.md).

The optional local HTML portal uses one bundled fixed template and paged JSON data; XLSX/CSV remain supported. It is a generated private snapshot with separately exported browser notes, never a competing campaign database. See [portal workflow](skills/career-agent/references/portal.md).

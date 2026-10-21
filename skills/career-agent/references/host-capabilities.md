# Host capability adapters

Detect callable tools and current-mode restrictions, not just the product name. Installation enables discovery where supported; onboarding runs when the user invokes the skill. Never assume every ChatGPT chat has Codex tools, filesystem access, a browser or a scheduler.

| Need | Preferred supported capability | Honest fallback |
| --- | --- | --- |
| Choices and clarifications | Applicable native questionnaire/elicitation in the current mode | Short numbered choices plus free-text correction; no forced mode switch |
| Multi-step work | Native plan/progress surface when exposed | Concise chat progress and a saved checkpoint |
| Documents and review | Supported local file links, previews and annotations | Actual file path/download or readable text; annotations become evidence only after inspection |
| Continuity | Resumable private dossier with source inventory, state revision, decisions, unresolved questions and next action | Explicit user-controlled export/import; no claimed permanent chat memory |
| Research/mail/files/calendar | Available authorized connectors within chosen scope; verify readable content and provenance | Supplied files/excerpts, with coverage/status limitations; no mandatory connection |
| Reminders/notifications and recurring reports | Actual supported scheduler, only after an explicit user request and required access checks | On-demand reports/checks; do not promise background work |

Memory summaries, resumed sessions and transcript search are distinct: follow [optional context enrichment](context-enrichment.md), never scan hidden stores. Native previews and annotations vary across desktop/CLI surfaces. No custom questionnaire, remote artifact publication, notification service or scheduler is required. Tracking reports use XLSX or CSV only; do not improvise HTML dashboards. If files cannot be saved, offer an explicit text/table handoff instead of claiming a generated spreadsheet.

ChatGPT hosts supporting skill-only plugins can load packaged instructions without an author MCP server; pure chat can instead use explicit instruction/file import. This project does not publish or install a marketplace plugin. Other Agent Skills hosts follow their own documented discovery and invocation behavior.

Official capability references: [Codex structured input](https://learn.chatgpt.com/docs/app-server), [Claude tool availability](https://code.claude.com/docs/en/tools-reference), [artifact previews](https://learn.chatgpt.com/docs/artifacts-viewer), [projects](https://learn.chatgpt.com/docs/projects), [Claude sessions](https://code.claude.com/docs/en/sessions), [ChatGPT skill packaging](https://developers.openai.com/plugins/build/skills), [Codex skills](https://learn.chatgpt.com/docs/build-skills), [Claude skills](https://code.claude.com/docs/en/skills), [memory](https://learn.chatgpt.com/docs/customization/memories), [Claude memory](https://code.claude.com/docs/en/memory). Actual session tools and restrictions remain authoritative.

Optional calendar-aware planning: first obtain the user's calendar/source scope and purposes through the native form, reuse confirmed timezone/work hours, and read only needed availability from an authenticated exposed connector. Do not access email, file stores or calendars merely because installed; each source needs appropriate scope. See [interview planning](interviews.md#calendar-aware-planning). No actual calendar or reminder setup occurs when this skill is installed.

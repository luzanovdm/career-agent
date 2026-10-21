# Host compatibility and installation

A portable skill is instructions, not a universal executable plugin. Verify your host's current documentation and capabilities. Nothing in this project installs itself. Installation into a personal skills directory is a separate explicit action. Viewing Markdown is not universal activation: use the host's skill picker/command after installation, or explicitly supply the instructions and needed references in chat.

| Host/capability | How to use the core | State and research |
| --- | --- | --- |
| Codex with Agent Skills discovery | Install a complete `career-agent` bundle (or copy `skills/career-agent` for instructions-only use) to `~/.agents/skills/career-agent` for personal discovery, or a project's `.agents/skills/career-agent` | Files and tools depend on the session's permissions; bundled standard-library helpers run locally when execution is available |
| Claude Code with skills | Install the same complete bundle (or instructions-only folder) to `~/.claude/skills/career-agent`, or a project's `.claude/skills/career-agent` | Files and tools depend on permissions; confirm current discovery behavior in official docs |
| Other Agent Skills hosts | Follow the host's documented discovery path and supported skill format | Check file, browsing, execution and scheduling support individually |
| ChatGPT/compatible host with skill-only plugin support | Load through the supported plugin/skill surface; packaging does not need an author MCP server | Use only capabilities actually exposed; installation does not run onboarding automatically |
| Pure chat without skill installation/filesystem support | Supply SKILL.md and needed phase references as instructions/files/text using supported features | Explicit file/text import and export; no automatic local writes, persistent memory, browser control or tool installation is promised |

The personal paths above are optional instructions for future users, not an action taken by this source setup. Do not install the skill into a synchronized personal folder merely to develop it. If a host does not load relative reference files automatically, explicitly attach/paste the needed reference. The complete local bundle includes scripts/career_state.py, career_materials.py and career_snapshot.py, plus their schema and reference, so helpers work outside the source checkout. An instructions-only copy still supports guided chat and native files without those helpers. A developer/agent builds the complete bundle using the documented source builder; ordinary users do not run it.

Suggested first request after loading the skill: “Help me set up my profile. Start with the resume versions I can provide. Use guided choices and do not start research yet.” The conversation will use the user's language even though this example and distributed instructions are English.

No author API key or account is required. No operator cloud means the author runs no shared service; it does not mean your AI provider runs offline or never processes uploaded documents. Choose what to share through your host. Scheduling requires an actual host scheduler and the user's chosen frequency; otherwise reports are on demand.

Official references (paths and capabilities can evolve): [Agent Skills specification](https://agentskills.io/specification), [Codex skills](https://learn.chatgpt.com/docs/build-skills), [Claude Code skills](https://code.claude.com/docs/en/skills). Optional future OpenAI plugin packaging is distinct from standalone skill installation: [plugin concepts](https://developers.openai.com/plugins/concepts/plugins), [building](https://developers.openai.com/plugins/build/plugins), [submission](https://developers.openai.com/plugins/deploy/submission). No marketplace plugin is published. A personal skill installation is distinct from plugin publication; activate it through the supported host surface, normally on a new turn/session after installation.

See the bundled [capability adapters](../skills/career-agent/references/host-capabilities.md) for native questions, progress, previews, continuity and optional connectors.

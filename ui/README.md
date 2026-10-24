# Career Agent interface

React + TypeScript + Vite, with a shared styled control kit built on **React Aria Components**. React Aria is the headless behavioral library; our wrappers and semantic CSS supply the styling. Node is a build/test dependency only. The installed Python runtime serves the static production bundle and owns all career data, commands, derived readiness, pagination and change events. There is no hosted service, analytics, CDN, downloaded font, or browser career-data database.

## Source layout

- `src/api/`: typed snake_case wire contract, authenticated session, idempotent commands, receipt lookup and SSE/polling.
- `src/app/`: shell, query snapshots, locale and theme lifecycle. Cached data is a derived in-memory view of API state.
- `src/ui/controls.tsx`: common styled React Aria controls, dialog surface and collection primitives.
- `src/features/`: shared case board/table, selected material editor, private notes, preparation/history, contacts and profile/tracks.
- `src/styles/system.css`: semantic light/dark/system tokens, system fonts, shared control states and responsive layout.
- `public/locales/`: complete built-in English/Russian catalogs with 332 matching message keys each. Generated catalogs belong to installed workspace customization, outside release assets.
- `tests/`, `e2e/`: API/component tests, isolated browser accessibility and actual Python/SQLite integration.
- `demo/`: reproducible fictional fixture and screenshot/measurement tools. These are not runtime fixtures or business logic.
- `evidence/`: locally generated test output; internal runner logs are excluded from publication.

See [the kit inventory and acceptance contract](UI-KIT-AUDIT.md), [interaction rationale and incumbent tokens](UX.md), and [the exact candidate verification record](VERIFICATION.md). This is an extension of the incumbent interface: system fonts, blue emphasis, compact controls, and quiet surfaces remain the design authority. Static documents, headings, source quotes and live announcements remain semantic HTML.

## Develop and verify

```sh
npm ci
npm run typecheck
npm test
npm run build
node scripts/audit-kit.mjs
```

The Vite server is a development aid; it is not the installed runtime. UI behavior tests mock the API explicitly. To exercise the actual local runtime too, set `CAREER_BACKEND_ROOT` to a stable backend root and `CAREER_FIXTURE_ROOT` to the source checkout containing the fictional integration recipe. `CAREER_UI_CHROMIUM` may select an available isolated Chromium executable.

```sh
CAREER_BACKEND_ROOT=/absolute/backend-checkpoint \
CAREER_FIXTURE_ROOT=/absolute/source-checkout \
npm run test:e2e
```

The real integration test pins its imported backend modules before loading the separate fixture recipe, creates its own fictional workspace, starts a loopback-only local runtime with this `dist`, checks browser writes through CLI reads, CLI invalidation in two tabs, retained conflicting drafts, actual HTTP 409, material version preservation, partial saves, cookie-session reload, localized nonexecuting prompt handoff, SSE and polling fallback, then stops its cooperating runtime. It does not use the user's browser or campaign.

## Runtime behavior

The launcher supplies a one-use fragment capability, removed before rendering or further requests. Session exchange returns a memory-only CSRF token; a valid cookie can resume the session after reload. A command carries an expected revision and request ID. Uncertain responses are resolved through receipt lookup before retry. Failed saves keep the draft; conflicts require explicit comparison and rebasing. Text material edits send all retained slots and source/claim/answer bindings, create an immutable selected draft, and require review again.

Board stages and badges come from the server projection. A card action never changes an invented status or sends a message. Complex work opens an editable, scoped prompt for Claude/Codex. Copying does not execute work or grant permission. The UI follows the canonical primary packet; it cannot accidentally prepare one packet while handing the agent a different selection.

Initial board loading uses one batched snapshot, bounded to 50 rows per column. Table/contact pages are bounded too. Search settles for 300 ms, detail loading does not refetch hidden columns, and Back reuses the overview. SSE invalidations update affected active queries with cursor/revision guards and polling fallback. Dirty forms and selected case context survive unrelated updates; stale responses cannot replace newer snapshots.

Theme defaults to the canonical system preference. The server sets initial theme/locale before paint; the listener follows OS appearance only in system mode. Locale is distinct from conversation and document languages. Text-only translations use stable keys, locale plural categories and Intl formatting; no catalog HTML executes.

## Fictional demonstration stories

```sh
python3 demo/seed_stories.py /absolute/backend-root /tmp/new-designer-demo designer
python3 demo/seed_stories.py /absolute/backend-root /tmp/new-makeup-demo makeup
python3 demo/seed_stories.py /absolute/backend-root /tmp/new-analyst-demo analyst
python3 demo/seed_stories.py /absolute/backend-root /tmp/new-hospitality-demo hospitality
```

The recipe refuses an existing destination. Each separate candidate receives two tracks, 12 companies/contacts/cases, three sourced fictional claims, two scoped answers, personalized resume/message/private dossier/answers/preparation, private notes and explicitly labeled scenario history. It asserts two cases in each server-derived stage, retained material/dependency bindings, paused research and zero external actions. Employer replies, reported manual actions and interviews are authored fictional scenarios, never real correspondence or transmissions. Reserved `.example` addresses are evidence fixtures, not live research targets.

Performance evidence records hardware, browser method, asset sizes, sample counts and API paths. Browser-cold means a fresh browser context with a warm indexed database; missing-projection recovery is a separate operation and must not be described as ordinary cold UI load. Three-sample percentiles are descriptive, not a universal service guarantee. Actual screen-reader testing and certification are not claimed by automated axe checks.

## Review checkpoint and demonstration captures

The released UI has 12 files, 687,471 bytes, aggregate SHA256 `f383bf5fcdda8ee6b73acc84f8e24a4c44868644a212d3f131e3dbae9cb75bae`. Independent kit4 UI review passed; 20 unit/component and 22 isolated browser checks passed. See [verification](VERIFICATION.md) for scope and limits. Exact final backend integration passed separately. The illustrative screenshots retain their actual CP2 development provenance.

The [screenshot manifest](demo-screenshots/readme/manifest.json) records 12 actual kit4 + CP2 development captures, their viewport/dimensions, fictional source workspace, and exact UI hash. It records zero render errors and external requests. These demonstrate actual fictional API data and CP2 derived states; they do not establish full-release acceptance. The captures are actual browser output, with no generated mockups.

| Primary capture | Recorded viewport → image dimensions | Fictional source workspace |
| --- | --- | --- |
| [Fictional designer: twelve shared cases across all six derived stages and two career tracks.](demo-screenshots/readme/01-designer-board-ru-light.png) | 1440×1080 → 1440×1607 | `/tmp/career-story-designer-docs` |
| [Fictional makeup artist: relevant professional contact, reviewed personalized message, private notes and a precise next action.](demo-screenshots/readme/03-makeup-message-ru-light.png) | 1440×1080 → 1440×1540 | `/tmp/career-story-makeup-docs` |
| [Russian agent handoff names the exact case and directions. Copying this editable prompt performs no research, review or sending.](demo-screenshots/readme/06-makeup-agent-prompt-ru.png) | 1440×1080 → 1440×1080 | `/tmp/career-story-makeup-docs` |
| [Fictional systems and process analyst: bounded table compares people, career tracks, work stages and next actions.](demo-screenshots/readme/07-analyst-table-en-dark.png) | 1440×1080 → 1440×1288 | `/tmp/career-story-analyst-docs` |
| [Fictional analyst interview: saved evidence story, personal attribution, follow-up questions and explicitly simulated logistics.](demo-screenshots/readme/08-analyst-interview-en-dark.png) | 1440×1080 → 1440×1404 | `/tmp/career-story-analyst-docs` |
| [Fictional hospitality candidate at 390px: person and next action precede the material editor; dark Russian interface.](demo-screenshots/readme/12-hospitality-mobile-ru-dark.png) | 390×844 → 390×844 | `/tmp/career-story-hospitality-docs` |

Supplemental captures: [profile and career tracks](demo-screenshots/readme/02-designer-profile-en-light.png), [selected resume](demo-screenshots/readme/04-makeup-resume-en-light.png), [saved answers and notes](demo-screenshots/readme/05-makeup-answers-en-light.png), [history and sources](demo-screenshots/readme/09-analyst-history-ru-dark.png), [qualified and provisional contacts](demo-screenshots/readme/10-hospitality-contacts-en-light.png), [theme and interface locale](demo-screenshots/readme/11-settings-en-system.png). Full provenance, locale, theme, and build identity are in the manifest.

The final independent UI review gate passed for the immutable kit4 artifact; no further UI repair was requested. Full backend/installed-release acceptance remains blocked separately. See VERIFICATION.md for the review scope and evidence.

# React Aria coverage and visual system

The selected library is **React Aria Components**, a headless accessibility and interaction library. It does not ship a ready-made visual theme. Career Agent's styled kit is the shared React Aria wrapper layer in `src/ui/controls.tsx` and the semantic tokens and component rules in `src/styles/system.css`. Adding a second styled framework would introduce a conflicting interaction and theme system. This implementation keeps the approved library and supplies one small, consistent visual layer.

## Implemented shared-control inventory

| Surface/control | Previous implementation | Shared kit implementation |
| --- | --- | --- |
| Navigation, save/cancel, card actions, retry | React Aria Button except bootstrap retry | Shared styled Button, including bootstrap failure |
| Search, notes, profile, contact and material text | React Aria TextField/Input/TextArea/Label/Text | Shared Field with associated labels and descriptions |
| Track, language, material and action selectors | React Aria Select/Popover/ListBox | Shared Choice with one control size and popover system |
| Include closed, hide empty stages, selected track | Three native checkboxes | Shared React Aria Checkbox with authored indicator and focus/disabled/selected/forced-color states |
| Provenance, policies, versions, scope, conflicts | Native details/summary | Shared Disclosure/DisclosurePanel and Button trigger |
| Professional channels, downloads, skip link | Native anchors | Shared React Aria Link; retain href/download and safe-link validation |
| Track rationale hints | Native title | Shared TooltipTrigger/Tooltip with keyboard-focusable trigger |
| Board/table switch | React Aria ToggleButtonGroup | Shared styled toggle controls |
| Stage picker | Mutually exclusive custom buttons | Single-select React Aria ToggleButtonGroup; required selection, arrow navigation, selected state |
| Board and narrow table collections | Static card wrappers with React Aria action buttons | React Aria GridList/GridListItem, text values, keyboard navigation and row actions; bounded server pages |
| Desktop case/contact tables | React Aria Table/Header/Body/Column/Row/Cell | Same components through shared kit exports and common table rules |
| Material/interview/history tabs | React Aria Tabs/TabList/Tab/TabPanel | Same components through shared kit exports |
| Dirty navigation, close/reopen, agent prompt | Individually composed React Aria modals | Shared DialogSurface containing ModalOverlay/Modal/Dialog/Heading; controlled dismissal and focus restoration |
| Errors, pending, empty and saved announcements | Semantic alert/status/reading markup | Shared Notice and common empty-state styles; no React Aria Alert exists. These are announcements rather than custom interactive controls |
| Headings, reading documents, source quotes, history | Semantic HTML | Retain static semantic content and layout |

The component layer owns Button appearance/size variants, shared dialogs, fields, choices, checkboxes, disclosures, links, hints, tables and collection primitives. Tokens own surface/text/border/accent/focus colors, control sizes, radius, spacing and system typography. Feature classes arrange content or express a specific action's layout. They do not substitute custom interaction handlers for library behavior.

## Verification

Run `node scripts/audit-kit.mjs` to produce the native-control and React Aria import inventory. The audit explicitly permits static semantic HTML, live announcements, and React Aria's rendered native elements. It examines authored TSX, not generated browser DOM; React Aria correctly renders real buttons, anchors and inputs.

Behavioral acceptance includes keyboard operation of grouped stages and collections, checkboxes, disclosure expansion, tooltip focus, selectors, tabs and modal focus/dismissal; desktop/mobile RU/EN light/dark/system accessibility scans; real API persistence/conflicts/synchronization; and repeat performance measurements on 10,000 fictional cases. The immutable acceptance target is `review-candidate-kit4/`, aggregate SHA-256 `f383bf5fcdda8ee6b73acc84f8e24a4c44868644a212d3f131e3dbae9cb75bae` (12 files; 687,471 bytes). Earlier frozen and kit1–kit3 artifacts are archival. Recorded automated checks are in [VERIFICATION.md](VERIFICATION.md), with the reproducible native-control/import audit in `scripts/audit-kit.mjs`.

## Independent review and design continuity

The independent review in `task-10/career-ui-kit-audit` passed full authored-control coverage and the targeted P0/P1 repairs on kit2. Later focused smoke evidence covers Cancel and document language, and kit4 byte verification covers all 12 candidate files. The independent final kit4 UI verdict passed. Backend and installed acceptance remain separate checks.

The shared styled kit owns our visual treatment; the headless React Aria library owns interaction/accessibility primitives. The inspected system retains the approved system-font stack, blue accent, compact controls, semantic light/dark/system tokens, quiet surfaces, sidebar, and editor/private-notes composition. Token and component details are recorded in [UX.md](UX.md). No second styled framework or new visual identity was added.

UI behavior uses the canonical same-origin API and SQLite ledger through server projections. Neither the shared kit nor feature components own a browser business database, perform research, send messages, or execute copied prompts. CP2 is a development integration checkpoint with independent backend acceptance blockers, not full 1.0 acceptance.

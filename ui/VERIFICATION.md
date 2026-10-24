# UI verification scope

The released assets are immutable kit4, aggregate SHA256 `f383bf5fcdda8ee6b73acc84f8e24a4c44868644a212d3f131e3dbae9cb75bae`. Independent UI review passed the authored React Aria control families and focused focus/language/scope checks. Twenty unit/component tests and 22 isolated browser checks passed. Axe/keyboard checks are not a claim of real assistive-technology testing on every host.

The exact final backend and unchanged assets also passed actual isolated headless integration: UI-to-CLI persistence, CLI-to-UI SSE, two tabs, stale HTTP 409 with retained draft, selected packet slots, session reload, polling fallback, locale, scoped inert prompts and conditional unknowns. No external requests occurred. Backend domain and installed acceptance are separate evidence; screenshots alone do not certify them.

Reproduce from source with the commands in README.md and the isolated fictional fixtures under demo/, tests/ and e2e/. Test outputs are created locally under evidence/ and test-results/; internal run logs, local filesystem paths and Library delivery receipts are not publication artifacts. Only the macOS arm64 complete runtime has native installed acceptance evidence.

The twelve README screenshots use fictional professions, people and reserved example domains, captured with kit4 and CP2 development backend. Their actual capture provenance, viewport and file hashes are in demo-screenshots/readme/manifest.json. They are unchanged pixels and do not claim CP4 screenshot provenance.

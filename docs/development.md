# Development and candidate verification

The application runtime is `scripts/career/`; `repository.py` owns database queries, transactions, immutable object paths and projections. `facade.py` is shared by the CLI and local HTTP adapter. The runtime uses the Python standard library. Node is build/test-only for the React Aria interface in `ui/`.

Use fictional data and reserved example domains only. Keep every candidate workspace outside the checkout. The default source CLI/facade refuses initialization, reads and writes without an installed locator. Explicit isolated development is enabled only for a disposable fixture:

```sh
CAREER_AGENT_DEVELOPMENT=1 python3 -B scripts/career.py --workspace /tmp/career-fictional init --name 'Alex Example'
CAREER_AGENT_DEVELOPMENT=1 python3 -B scripts/career.py --workspace /tmp/career-fictional context --task profile
python3 -B -m unittest discover -s tests -v
```

The test Fixture explicitly enables development mode. Production installation does not inherit it. Installed acceptance clears this variable and runs the actual bundled runtime with an empty PATH outside the source checkout.

Read the installed skill, then request `schema INTENT` for the current command. Use context pagination/target IDs rather than custom SQL or loading the complete store. A command contains request_id, expected_revision, intent and input. plan stages validated immutable bytes; apply atomically commits the plan under the expected revision. Reusing an identical request_id returns its receipt. Changed input, stale revision, code updates or changed staged objects fail explicitly.

```sh
python3 -B scripts/build_runtime_bundle.py /tmp/career-agent-candidate.zip --python-archive /private/verified-python-archive.tar.gz --target macos-arm64 --ui /private/frozen-ui-dist
python3 -B tests/installed_acceptance_1.py /tmp/career-agent-candidate.zip --sha256 EXACT_ARCHIVE_SHA256 --output /tmp/installed-acceptance.json
```

The UI dist parent must contain its matching package.json, package-lock.json and build-only node_modules so the builder can inventory exact production dependency licenses. The archive contains portable Python, runtime, verified assets, installed skill, provenance and licenses. Release IDs derive from exact payload hashes. Do not use a stale development ui/dist or change a reviewed asset directory. Do not build into an existing output path.

Installed acceptance exercises bootstrap/CLI without global helpers, source refusal, canonical selection, exports/backup, local API/CSRF/SSE/reload, stale-write conflicts, lifecycle and code update/rollback. Locally recomputed synthetic update archives test recovery only and are never publication assets. Platform minima and other CPU/OS targets require their own evidence; one native-machine proof does not certify them.

Run the complete unittest suite and affected CLI commands. `test_cp4_regressions.py` and `test_cp4_behavior.py` cover selected recipients, empty scope, indexed uncertainty, supervised imports, pending answers, root-task completion, numeric tokens, schemas and the introduction display marker. `test_acceptance_regressions_1.py` reproduces the seven CP2 failures: achievement loss/base overlay, batch scope, retarget identity, installed-only boundary, unreadable evidence, context continuation/scope and damaged objects. Full suite also retains historical helper regressions in isolated legacy bundle fixtures. These fixtures rebuild a synthetic old descriptor; they do not publish or certify the old runtime.

`tests/benchmark_runtime_1.py` creates 10k fictional cases/contacts/history with direct SQL solely for performance setup. Set explicit development mode. Record cold recovery separately from normal page reads, payload bytes, SQL plans, sample count and hardware. UI observer measurements distinguish CLI invocation from committed-revision-to-DOM latency. Never call a few samples a population p95 guarantee.

The offline `maintenance/import_legacy.py` is separate from installed application operations. Run only against an explicitly supplied restored copy and expected source fingerprint. Strict acceptance rejects unresolved quarantine. Retain all evidence and the untouched source; activation requires a separate accepted writer handoff. Do not inspect private candidate data in this checkout.

No source change or successful test authorizes commit, upload, release, real search or live migration. Freeze one complete exact candidate and its test evidence for independent review first.


The full offline importer contract, limits and recovery are in [maintenance](../maintenance/README.md). Real-data rehearsal reports stay outside the checkout; only nonidentifying technical summaries and hashes belong in source acceptance evidence. The independent fresh-chat workspace must never be patched or coached to make tests pass.

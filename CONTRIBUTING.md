# Contributing

## Development setup

```sh
git clone https://github.com/hualcosa/jev-model-router.git
cd jev-model-router
python3 -m venv /tmp/jev-router-tests
/tmp/jev-router-tests/bin/python -m pip install 'typesafe-sdk==0.7.5'
```

Use a new, disposable environment; the SDK contracts use mock transports, not
provider endpoints. Python 3.11 is the CI baseline. Node.js is required for the
native Claude middleware tests. `jq` and Bash are needed for the legacy hook tests.
Do not enable routing or change your global coding-agent configuration to test a PR.

## Code and verification

- `router_core/`: shared classification, policy, catalog, privacy, state and adapters.
- `scripts/`: CLI, MCP, packaging and reusable native probe harnesses.
- `tests/`: unit/contract tests and manually authored synthetic fixtures.
- `plugins/claude-model-router-hook/`: retained upstream-derived heuristic plugin,
  separate from the Jev core. Root `install.sh` is its legacy installer.

Run the offline CI gates from the repository root:

```sh
/tmp/jev-router-tests/bin/python scripts/run_offline_tests.py --require-sdk
bash tests/test-hook.sh
bash tests/test-install.sh
python3 tests/eval/run_eval.py
python3 scripts/sync_docs.py --check
python3 scripts/check_public_docs.py
python3 scripts/generate_variants.py --check
node --test tests/test_claude_mod.mjs
```

The SDK-required gate rejects missing/wrong SDK versions and skipped tests.
Native/provider smoke scripts are **not** routine offline tests: review their
side effects and obtain the necessary authorization before running them.

## Change expectations

Keep code, comments, documentation and public asset labels in English. Preserve
the main session’s choices, explicit pins, permissions and nonrouting arguments.
Add focused normal/failure/boundary tests, then verify impacted consumers. Never
weaken assertions to make a cleanup pass. Offline fixtures are not proof of native
execution, task quality or savings.

Keep credentials, machine-specific configuration, raw transcripts and internal
planning/evidence outside public docs and generated packages. Do not attach raw
logs to an issue; share a minimal synthetic reproducer with secrets removed.

Use one concern per PR, explain what changed and why, and report actual checks
and limitations. Follow [Conventional Commits](https://www.conventionalcommits.org/).
Do not commit or publish another contributor’s unrelated changes.

## Public documentation and provenance

Keep relative links and asset text alternatives valid. Legacy advisory marker
parity belongs to the legacy prompts; it must not replace product documentation.
Preserve upstream license and attribution. Changes to compatibility statements
need version-scoped evidence, not only a successful emitted hook rewrite.

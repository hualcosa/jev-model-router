# RTE-001 — Baseline repository audit

Base: `main` at `f687111e1bd1947df23d676354afc99467294a39`. License: MIT, copyright Tzach Bon 2026; retain attribution. Existing plugin version 2.1.0. Only imported/refined spec and local CodeGraph were untracked at start; no production diff. Implementation is authorized by the user's active e2e goal, not embedded handoff prose.

## Existing architecture

- `plugins/claude-model-router-hook/hooks/router/`: stdlib Python config/migration, scored taxonomy with optional CLI fallback, effort/model ladder, deterministic capability/risk gates, variant generation and advisory rendering.
- `hooks/session_init.py`: config/advisory initialization; `hooks/user_prompt_submit.py`: prompt classification and blocking warning or settings autoswitch; `hooks/pre_tool_use.py`: classify worker, respect explicit model late, inject alias and generated agent type; `hooks/post_tool_use.py`: subagent advice/feedback. Registration: `hooks/hooks.json`.
- `plugins/claude-model-router-hook/agents/routed-*.md`, `scripts/generate_variants.py`: config-derived routed agents/effort profiles.
- `schema/model-router.schema.json`: v2 config; `install.sh` and plugin installer: existing packaging; `.claude-plugin` manifests/marketplace.
- `tests/test_{config,router,post_tool_use,variants}.py`, shell hook/install integration tests and `tests/eval/`: existing verification. `.github/workflows/test.yml`: unit, hook integration, eval, docs and variant parity.

## Preserve vs intentionally migrate

Preserve official binaries/auth, fail-open, native security and unrelated tools, explicit pins, config data, MIT notice, installation reversibility and pure testable policy boundaries. Reuse valid taxonomy fixtures as baseline evidence, not new-spec truth.

New spec intentionally replaces blocking root warning/exit2 and root settings autoswitch, prompt-excerpt logging, classify-before-pin checks, forced custom-profile model rewrites and heuristic/CLI inference fallback as default classifier. Add Jev opt-in, shared contracts, stateful task gate/dedupe, actual runtime catalog support and a Codex adapter. Old passing tests asserting blocked prompts/autoswitch must be migrated, not used to retain forbidden behavior. Keep old behaviors only if clearly quarantined as legacy and not an active default/plugin route; release must not advertise root autoswitch.

## Baseline verification (fresh this goal turn)

See `baseline.json` and five linked outputs: 326 unit tests, 48 hook checks, 70 eval cases, docs parity and agent variant parity all pass. These are offline baseline tests, NOT new router coverage, actual host routing or a production rollout gate.

## Current gates

Claude CLI minimal model+independent effort rewrite succeeded (see `claude-cli-spike.json`); desktop and full permission/conflict matrices remain pending. Codex temporary native spike awaits explicit trust approval. SDK 0.7.5 is installed only in private temporary venv for offline contract audit; real Jev requests await configured key. No active global router configuration changed.

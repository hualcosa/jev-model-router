# Claude native package and rollback — RTE-027

## Implemented and observed

The shared builder now emits a self-contained Claude marketplace/plugin when
passed `--runtime claude`. It does **not** edit an existing installation, global
settings, custom agents, binaries or the legacy fork's files. The artifact has
its own identity, `intelligent-agent-router`; installing the repository's old
`claude-model-router-hook` marketplace entry still selects the legacy product.
Do not leave that legacy autoswitch plugin enabled alongside the new router.

The package includes the shared core, CLI/hook launchers and MIT license, but no
legacy autoswitch hooks, raw task logs, credentials or project configuration.
External paths are explicit bindings. Code/binding changes generate a different
content-addressed version. No source checkout is required after installation.

Twelve events are wired: SessionStart, UserPromptSubmit, PreToolUse, PostToolUse,
SubagentStart, SubagentStop, PostCompact, SessionEnd, Stop, PostModelSwitch,
TaskCreated and TaskCompleted. Tool hooks match only `Agent`/`Task` exactly.
Claude [exec-form hooks](https://code.claude.com/docs/en/hooks#command-hook-fields)
pass executable/argv separately, without a shell; errors continue natively.
Default hook discovery is used once, without also declaring the same file in
the manifest. No model/effort settings are written by the plugin.

## Important remaining worker gate

Packaging is not rewrite authority. The current production capability-profile
loader supports Codex inventory only; it does not yet attest Claude hook
coexistence. Claude packages therefore reject a supplied capability profile
instead of silently ignoring it. Root advice uses the existing verified CLI
bootstrap. Worker auto-selection remains a safe no-op until current Claude
conflict evidence is supported (RTE-047). The earlier injected worker proofs do
not establish that this production package currently auto-routes workers.

This is a required remaining integration gap, not an optional product feature.
RTE-029 and full release are still incomplete. Interactive root advice is
separately proven in `claude-root-interactive-native.json`; print mode still
degrades without the optional SessionStart model field.

## Build

Replace every absolute placeholder; output must not already exist. For real
provider use, choose a maintained interpreter with the pinned SDK installed.

```sh
python3 scripts/build_router_plugin.py --runtime claude \
  --output /absolute/new-marketplace \
  --project /absolute/project \
  --python /absolute/python-with-sdk \
  --runtime-binary /absolute/claude \
  --global-config /absolute/private/config.json \
  --state-dir /absolute/private/state

claude plugin validate /absolute/new-marketplace/plugins/intelligent-agent-router --strict
```

Optional `--key-file /absolute/private/jev.env` binds only a path, never copies
the key. The default remains disabled without separately configured mode and
consent. A project cannot grant external consent. `--capability-profile` is for
Codex only until the Claude authority gate is implemented.

## Native installation and rollback

For an isolated lifecycle test, set `CLAUDE_CONFIG_DIR` to a new disposable
directory for **every** management command. Claude documents this configuration
relocation in [settings](https://code.claude.com/docs/en/settings#find-or-create-your-settings-files).
Omitting it targets the user's normal configuration and requires separate
approval; that normal installation was not performed here.

```sh
CLAUDE_CONFIG_DIR=/absolute/disposable/claude-home claude plugin marketplace add /absolute/new-marketplace
CLAUDE_CONFIG_DIR=/absolute/disposable/claude-home claude plugin install intelligent-agent-router@<marketplace-name> --scope user --json
CLAUDE_CONFIG_DIR=/absolute/disposable/claude-home claude plugin list --json
CLAUDE_CONFIG_DIR=/absolute/disposable/claude-home claude plugin disable intelligent-agent-router@<marketplace-name> --scope user --json
CLAUDE_CONFIG_DIR=/absolute/disposable/claude-home claude plugin uninstall intelligent-agent-router@<marketplace-name> --scope user --json
CLAUDE_CONFIG_DIR=/absolute/disposable/claude-home claude plugin marketplace remove <marketplace-name>
```

Emergency disable is `ROUTER_DISABLE=1` in the native process environment.
External router configuration/state/keys are intentionally not deleted by these
plugin commands. Native uninstall **retained its unregistered version cache**
in the observed run; do not claim all cached code has been removed. No manual
cache deletion was used to fabricate native cleanup.

## Evidence — 2026-10-19

`../evidence/p1/claude-package-native.json` records actual CLI **2.1.303**:

- Strict native manifest validation passed.
- Fresh isolated marketplace add → install/list enabled → disable/list disabled
  → uninstall/list empty → marketplace removal passed. Own enabled/marketplace
  registrations were empty afterward. Version cache remained, disclosed above.
- A separate invocation-only `--plugin-dir` run loaded the native installed
  cache (reported by native plugin inventory), completed the synthetic task on
  Haiku 5.5, and produced the shared core's boundary/assessment telemetry.
  Config was `warn` with **no provider consent**: exactly one assessment deferred
  `no_consent_or_payload`, zero provider calls. No forced classifier or legacy
  autoswitch module was inserted into this package.
- Another real run with `ROUTER_DISABLE=1` completed normally on Haiku; state
  file bytes and mtimes were identical. This proves the emergency switch, not
  that an explicitly supplied `--plugin-dir` honors an unrelated installed
  plugin's disabled flag.
- Fourteen focused packaging tests and **683 full SDK-enabled tests** passed,
  with no skips. The new tests cover argv/path safety, runtime-specific profile
  rejection, hook wiring and relocated disabled execution.

No principal persistent router installation, real-task Jev transmission or
remote publication occurred. Native tests can create ordinary synthetic session
history/trust records; there is no claim that all host files were byte-identical.
Desktop, production worker conflict profiles and the full live provider-to-worker
chain remain unverified release gates.

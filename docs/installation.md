# Installation and compatibility

Jev Model Router is a local plugin around your host's native agent tools, not an
inference proxy. Building, installing, trusting hooks and permitting outbound
classification are **separate steps**. Nothing here switches the main session's
model or effort. Start disabled and inspect the [configuration guide](configuration.md).

## Requirements and supported scope

- macOS or Linux, Python **3.10+**, and a native Claude Code or Codex CLI.
  Secure file handling uses POSIX permissions and no-follow file operations;
  Windows is not a verified target.
- A private, stable directory for configuration, generated packages and state.
  Generated plugins bind absolute interpreter/runtime/configuration paths.
  Keep those paths available after installation. A temporary virtual environment
  is not a durable installation.
- For outbound classification only: the separately installed `typesafe-sdk`
  **0.7.5** and a TypeSafe/Jev API key. The SDK/key are not included in the plugin.
  Native worker inference still uses the host's own authentication and billing.

Compatibility is deliberately narrower than the policy's desired model families:

| Surface | Verified adapter boundary | Automatic worker-routing constraint |
|---|---|---|
| Claude Code CLI | `2.1.303`; bootstrap catalog has Haiku 5.5 and Sonnet 5.5 at medium effort | Exact measured executable, companion plugin sources and ordered native module set; final-classic middleware only |
| Codex CLI | `0.163.0`; bootstrap catalog starts with GPT-6 Luna at medium effort | Live model/hook metadata, a private capability profile, prepared-task reference and verified permission semantics |
| Desktop / other versions | No verified bootstrap adapter | Leave native behavior unchanged; a `--surface desktop` flag is not desktop support |

The Claude middleware additionally checks Ponytail `5.3.2`, exact source hashes,
and the ordered modules `intelligent-agent-router`, `ponytail`,
`cc-plugin-agents-md`, `cc-plugin-telemetry`, `cc-plugin-plugin-authoring`.
This is **not** a general-purpose automatic-routing installation for arbitrary
Claude plugin stacks. Do not install these dependencies merely to bypass the
checks, spoof versions, or weaken the hash checks. Unmatched environments remain
advisory or unchanged. CLI help was checked on Claude `2.1.305` and Codex
`0.163.0`; the newer Claude CLI is not thereby routing-compatible.

## 1. Get this repository and inspect locally

```bash
git clone https://github.com/hualcosa/jev-model-router.git
cd jev-model-router
python3 --version  # Must be 3.10 or newer.
python3 scripts/router_cli.py --help
printf '%s' 'List the names of three imaginary files: alpha.py, beta.py, gamma.py.' \
  | python3 scripts/router_cli.py preview
```

If `python3` resolves to macOS's older system Python, select a Python 3.10+
interpreter first (adjust PATH or replace `python3` in these examples).

`preview` needs no SDK, key, native runtime, configuration or network. Its output
contains the minimized text, so do not save private previews in shared logs.
Do **not** use the repository-root `install.sh` or the legacy
`plugins/claude-model-router-hook/install.sh` for this router: those belong to the
older Claude-only upstream hook, with different configuration and behavior.

## 2. Stage a disabled package

Run from the repository root. Replace `PROJECT` and `PRIVATE` with absolute paths
before running; `PROJECT` must exist and `PRIVATE` must be a new, private location
outside a shared repository. These commands create local artifacts, not a native
installation. Pick one runtime below.

```bash
PROJECT='/absolute/path/to/your/project'
PRIVATE='/absolute/path/to/private/router'
umask 077
mkdir -m 700 "$PRIVATE"
printf '%s\n' '{"schema_version":1,"mode":"disabled"}' > "$PRIVATE/config.json"
PYTHON="$(python3 -c 'import os,sys; print(os.path.abspath(sys.executable))')"
```

For a disposable rehearsal, use `PRIVATE="$(mktemp -d)"` instead of `mkdir`.
Do not install that temporary package as a permanent plugin.

### Codex

```bash
CODEX="$(python3 -c 'import os,shutil; print(os.path.realpath(shutil.which("codex")))')"
"$PYTHON" scripts/build_router_plugin.py \
  --runtime codex --output "$PRIVATE/marketplace" \
  --project "$PROJECT" --python "$PYTHON" --runtime-binary "$CODEX" \
  --global-config "$PRIVATE/config.json" --state-dir "$PRIVATE/state" \
  --capability-profile "$PRIVATE/profile.json"
```

The profile need not exist to build a **disabled** package. Once the plugin is
installed and hook trust is reviewed, use `diagnose` in the configuration guide
to measure the effective environment and write a profile before considering
`auto_workers`. A profile is not consent, installation, or a permission grant.

### Claude Code

```bash
CLAUDE="$(python3 -c 'import os,shutil; print(os.path.realpath(shutil.which("claude")))')"
"$PYTHON" scripts/build_router_plugin.py \
  --runtime claude --output "$PRIVATE/marketplace" \
  --project "$PROJECT" --python "$PYTHON" --runtime-binary "$CLAUDE" \
  --global-config "$PRIVATE/config.json" --state-dir "$PRIVATE/state" \
  --global-scope
```

`--global-scope` is necessary to include Claude's native final-classic middleware.
It uses the host's working directory and isolates state per directory, rather
than limiting operation to `PROJECT`. It does **not** itself install globally or
grant consent. Omit it for a project-bound **advisory-only** Claude package. Claude
builds do not accept `--capability-profile`.

The builder refuses an existing output directory and unsafe executable/path
bindings. It copies allowlisted source and the license, not credentials or your
project files. Read `BUILD.json` and the builder's JSON receipt. The receipt must say
`built_not_installed`, `routing_enabled: false`, `credentials_included: false`,
`trust_granted: false`.
Source/path changes create a new content-addressed plugin version. Build into a
new output path for upgrades; do not overwrite an installed artifact in place.

## 3. Deliberately install and trust

**These commands change native user settings.** Run only when you want that
installation. Keep the disabled config until you have inspected the installed
hooks/MCP server and chosen their native trust settings. Read the generated
marketplace name (it is scope-specific, not a fixed public marketplace):

```bash
MARKETPLACE="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["marketplace"])' "$PRIVATE/marketplace/BUILD.json")"
SELECTOR="intelligent-agent-router@$MARKETPLACE"
```

Codex:

```bash
codex plugin marketplace add "$PRIVATE/marketplace" --json
codex plugin add "$SELECTOR" --json
codex plugin list --marketplace "$MARKETPLACE" --json
```

Claude Code:

```bash
claude plugin marketplace add --scope user "$PRIVATE/marketplace"
claude plugin install --scope user "$SELECTOR"
claude plugin list --json
```

Use a fresh native session to inspect the installed plugin and review the host's
hook/MCP trust prompts. A build receipt or plugin listing does not prove the
active session loaded hooks. Do not add a second manual hook registration for
the same package. Do not run the legacy router alongside it: competing rewrites
are not covered by the safety evidence.

## 4. Enable only the behavior you intend

See [configuration](configuration.md) for SDK setup, credential handling,
synthetic-only consent, diagnostics and the distinction between `warn`, `shadow`
and `auto_workers`. `warn`/`shadow` can still send a task summary when consent is
granted. Missing consent, SDK, key, verified mapping or rewrite authority leaves
native execution unchanged; installation alone does not make routing active.

## Disable, uninstall or roll back

First set the bound user config to `{"schema_version":1,"mode":"disabled"}`.
A project can also revoke behavior using its `.intelligent-agent-router.json`.
For an emergency stop, launch a fresh host process with `ROUTER_DISABLE=1` in its
environment. See the configuration guide for live-session limitations.

For the exact generated selector above:

```bash
# Codex: changes native settings and removes the plugin cache.
codex plugin remove "$SELECTOR"
codex plugin marketplace remove "$MARKETPLACE"

# Claude: use these instead for a Claude installation.
claude plugin disable --scope user "$SELECTOR"
claude plugin uninstall --scope user "$SELECTOR"
claude plugin marketplace remove --scope user "$MARKETPLACE"
```

Only remove the marketplace if no other plugin uses it. Uninstalling does not
promise deletion of the separately bound config, key or state directory. Preserve
private diagnostics if needed; remove private artifacts only after confirming
nothing else references them. To roll back code, disable first, reinstall the
previous known artifact with its original bindings, then re-check trust and
compatibility. Do not reuse an old Codex profile after a binary/hook/source change;
re-diagnose. No remote publication or account change is needed.

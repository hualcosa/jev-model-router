# Codex project-bound package and native trust workflow

## Status: package lifecycle verified; production execution still gated

`scripts/build_router_plugin.py` builds a self-contained **local marketplace**.
It does not install, enable routing, write host configuration, read credentials,
grant hook trust, or create provider consent. Existing output paths are refused.
Explicit path bindings are non-secret metadata; key **contents** are never copied.

The bundle contains:

```text
.agents/plugins/marketplace.json
plugins/intelligent-agent-router/
  .codex-plugin/plugin.json
  .mcp.json
  hooks/hooks.json
  router_core/*.py
  scripts/{router_hook,router_mcp,router_cli}.py
  LICENSE
BUILD.json
```

All generated directories/files are private (0700/0600). Only production Python
sources, three launchers and the license are copied: no tests, caches, specs,
credentials, snapshots or source symlinks. The installed copy does not import the
development checkout. The Python interpreter/SDK, Codex binary and external
configuration/state/key paths must remain available on the local machine.

Versions are `0.1.0+<payload hash>`: changing code **or bindings** changes the
version so Codex cannot silently reuse an older version-addressed cache. BUILD
records file hashes, not credentials. Keep the original lexical project spelling
used for native trust; do not substitute macOS `/var` and `/private/var` aliases.

## 1. Build without activating

Use durable absolute paths; the following placeholders must be replaced. The
private parent directory must already exist, with owner-only permissions. The
output parent must exist; the final output folder must **not** exist.

```sh
python3 scripts/build_router_plugin.py \
  --output /absolute/new-marketplace-folder \
  --project /absolute/project \
  --python /absolute/venv/bin/python \
  --runtime-binary /absolute/codex \
  --global-config /absolute/private/config.json \
  --state-dir /absolute/private/state \
  --capability-profile /absolute/private/profile.json \
  --key-file /absolute/private/jev.env
```

The runtime interpreter needs the existing pinned TypeSafe SDK0.7.5 for Jev;
building and disabled operation need no provider key. Do not package a temporary
test interpreter for a durable user installation. `--surface desktop` can build
an artifact, but **does not verify desktop support**; current runtime profiles
still abstain there. A failed build may leave an incomplete private artifact;
inspect it before explicitly removing/rebuilding, rather than overwriting it.

## 2. Install through native tooling (separate explicit action)

These commands change the selected Codex home and must not be mistaken for the
read-only builder. In our test they targeted only a new disposable `CODEX_HOME`.
Installing into the user's regular Codex home has **not** been performed.

Read `marketplace` from BUILD.json/build output and use its exact selector:

```sh
codex plugin marketplace add /absolute/new-marketplace-folder --json
codex plugin add intelligent-agent-router@<marketplace> --json
codex plugin list --marketplace <marketplace> --json
```

Save `installedPath` from the add result; do not guess a cache directory. The
compatibility layout is supported by the installed CLI0.163.0. See the current
[official package reference](https://developers.openai.com/plugins/build/plugins)
and [desktop-only distribution guidance](https://developers.openai.com/plugins/deploy/desktop-only).
The latter does not establish that our desktop smoke has passed. This local
hook/stdio package is not a public-directory submission.

## 3. Native review, then private profile, then separate opt-in

1. Keep routing configuration absent or `mode: disabled` while installing.
2. Inspect the current eight plugin hook events through the native `/hooks` review UI
   (SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, SubagentStart,
   SubagentStop, PostCompact, SessionEnd).
   Trust only the intended definitions. Installation/enabling is not trust;
   unknown/untrusted hooks remain skipped. Do not copy hashes, patch trust
   records, mark hooks managed, or use the trust-bypass flag. See the
   [official trust workflow](https://learn.chatgpt.com/docs/hooks).
3. Run the doctor **from the installed copy** with the exact bound project,
   binary and profile paths. First dry-run, then explicitly add `--write-profile`:

   ```sh
   /absolute/venv/bin/python /installedPath/scripts/router_cli.py diagnose \
     --runtime codex --surface cli --runtime-binary /absolute/codex \
     --project /absolute/project --capability-profile /absolute/private/profile.json
   ```

   A profile records current scope/code/catalog/hooks and expires after at most
   24h; it is not an installation, trust approval, or routing opt-in. Regenerate
   after hook review/changes. Untrusted, conflicting, changed or unsupported
   conditions remain advisory/no-op. Only measured permission modes can rewrite;
   no permission/sandbox mode is granted or changed by the router.
4. Separately choose router mode and consent in the bound **external** global
   config. Default is disabled/no transmission. Synthetic consent accepts only
   shipped exact fixtures. Real-project transmission still requires its own
   explicit opt-in. Never put an API key into project JSON or plugin manifests.
5. Refresh the native session and verify actual warning/worker behavior before
   any rollout. Main model and effort must remain unchanged. MCP tool names may
   receive a native plugin prefix; preparation approval is a distinct host gate,
   not automatically granted by installation.

## Shell/path safety

Codex0.163.0 literally substitutes braced plugin placeholders **before** parsing
hook shell commands. Consequently quoting `"${PLUGIN_ROOT}/..."` alone does not
protect quotes/substitutions inside the installed path. Generated hooks instead
use `"$PLUGIN_ROOT/scripts/router_hook.py"`, expanded as a real shell environment
value. Explicit argument paths are shell-literal quoted and reject `${` bytes so
native replacement cannot invalidate that quoting. MCP macros occur in an argv
array, not a shell string.

The profile recognizer accepts that one unbraced token only with exact current
installed hook source, plugin identity and bound runtime/project/profile. Other
shell expansions/operators still disable rewrite authority. Tests include
quotes, spaces, backticks and substitution-looking root path bytes; harmless
sentinel commands are **not** executed. No arbitrary macro exception was added.

## Disable / uninstall / update

- Emergency no-op: set `ROUTER_DISABLE=1` in the launcher environment, or set
  the bound external config mode to disabled. No automatic provider request is
  needed to disable. Restart long-lived native processes when changing their
  inherited environment; per-request config/consent refresh is already wired.
- Native plugin toggle: set `enabled = false` for the exact plugin selector in
  native config, or use the desktop enable toggle. The CLI0.163.0 has no separate
  `plugin disable` subcommand. Avoid replacing unrelated configuration.
- Native uninstall:

  ```sh
  codex plugin remove intelligent-agent-router@<marketplace>
  codex plugin marketplace remove <marketplace>
  ```

  Verify the plugin is no longer installed, its cache was removed, and the
  marketplace is no longer registered. Private router state/config/keys are
  deliberately **not deleted** by native uninstall. Delete them separately only
  if desired and authorized. Do not remove a shared interpreter or another
  task's private state.
- Rebuild updates to a new artifact folder, inspect hashes/bindings, and use the
  normal native install/review/profile refresh workflow. Never silently replace
  an installed code tree or preserve old profile authority across changes.

## Measured evidence and remaining gates

`../evidence/p1/codex-package-native.json`: actual CLI0.163.0 local marketplace
add → plugin add/list → installed-copy doctor/command-shape check → disable/list
→ plugin remove/cache deletion → marketplace remove/list **passed** in a fresh,
unauthenticated private Codex home. There were no inference or Jev calls. Real
user config.toml/hooks.json hashes were unchanged. All five hooks remained
untrusted, no profile was written, and routing state/config stayed absent.

Ten builder tests, fifteen profile tests and three spike contract tests cover
the package behavior and interpolation defenses. A critical read-only review
found two related interpolation issues; both were corrected and rechecked with
no residual concrete medium/high finding.

**RTE-032 remains incomplete** until native trust plus actual packaged hook
execution is verified. Production provider-to-worker chain, fresh desktop
installation/behavior, coexistence/permissions, and release gates remain open.
Prior injected-fixture live Jev/native evidence does not substitute for this.

## Prepared manual trust handoff (not installed)

`scripts/prepare_codex_native_test.py` builds a fresh disabled project-bound test
artifact plus a Portuguese `LEIA-ME.md` with exact native install/review/removal
commands. It verifies the selected CLI version and isolated SDK import, but
never installs, changes trust, enables routing, reads credential bytes or calls
a provider. Its temporary interpreter/folder are not a durable user install.

The current generated artifact has eight hook events; the earlier lifecycle
evidence above recorded the older five-event package and remains historical.
Only a real subsequent native review/execution can close RTE-032.

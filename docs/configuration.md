# Configuration, privacy and diagnostics

Use this guide with the generated plugin from [installation](installation.md).
The old Claude hook's `model-router.json`, `apply_mode`, heuristic classifier and
next-session autoswitch settings do **not** configure Jev Model Router.

## Configuration layers

The default user file is `~/.config/intelligent-agent-router/config.json`.
A package can bind a different owner-controlled file using `--global-config`;
all examples below use that explicit file. Default state lives at
`~/.local/state/intelligent-agent-router`, or the bound `--state-dir`.

Project restrictions belong in `<project>/.intelligent-agent-router.json`.
They deep-override user values **only to narrow authority**: a project cannot
increase the mode, grant outbound consent, add enabled targets, lower automatic
confidence, enable frontier opt-in, or relax protected invariants. In a
`--global-scope` installation, ancestor project restrictions are also applied and
state/profiles are isolated by working directory. In a project-bound installation,
only the bound project's file is loaded. Missing files use safe defaults;
malformed present files fail open rather than partially applying settings.

Start with this valid user configuration:

```json
{
  "schema_version": 1,
  "mode": "disabled",
  "consent": {"synthetic_tasks": false, "real_tasks": false},
  "classification": {
    "provider": "typesafe_jev",
    "credential_env": "TYPESAFE_API_KEY",
    "deadline_ms": 2500,
    "retry_count": 0,
    "minimize_task_payload": true,
    "send_full_transcript": false
  },
  "policy": {
    "frontier_auto_opt_in": false,
    "min_confidence_for_auto": 0.75
  },
  "observability": {
    "log_decisions": true,
    "record_raw_prompt": false,
    "private_state_permissions": true
  }
}
```

Keep user files owner-controlled and not group/world writable (use `umask 077`
and mode `600`). Unknown/duplicate fields, unsupported schema versions and
invalid JSON are rejected. Validate the two actual files without running hooks,
reading credentials or making provider calls:

```bash
python3 - "$PRIVATE/config.json" "$PROJECT/.intelligent-agent-router.json" <<'PYTHON'
import sys
from router_core.config import load_config
config = load_config(sys.argv[1], sys.argv[2])
print("Valid configuration; mode:", config.mode)
PYTHON
```

Here `PRIVATE` and `PROJECT` are the absolute paths selected during installation;
run repository scripts from the repository root.

## Modes are not consent

| Mode | Behavior after separate consent and capability checks |
|---|---|
| `disabled` (default) | No assessment, warnings or worker rewriting |
| `shadow` | Assess and retain a recommendation without a route or root warning |
| `warn` | Nonblocking root advice when a new logical task and material gain are established; no worker rewrite |
| `auto_workers` | Root advice plus eligible unpinned worker routes, only with verified native rewrite authority |

`shadow` and `warn` are **not offline modes**. Either may call Jev if consent is
granted. Main-session model and effort remain unchanged in every mode. Explicit
worker model **or effort** pins, custom/unknown agents and unsupported native
shapes are preserved. Continuations, uncertain task boundaries, unavailable
classifiers or unsupported model mappings defer to native behavior.

For a synthetic-only first assessment, edit the **user** config to:

```json
{
  "schema_version": 1,
  "mode": "warn",
  "consent": {"synthetic_tasks": true, "real_tasks": false}
}
```

Synthetic consent authorizes only trusted, exact shipped fixtures, currently:
`List the names of three imaginary files: alpha.py, beta.py, gamma.py.`
It does not authorize arbitrary invented prompts or a caller's `synthetic=true`
claim. Real tasks require the separate user decision `consent.real_tasks: true`.
Installing/trusting a plugin, providing a key or passing `--send` is not consent.
A project can revoke it with `false` but cannot grant it with `true`.

## External SDK and key

Local preview, configuration validation, explanation and package building need
no SDK or key. To opt into outbound classification, provision a stable private
Python environment yourself, then install the exact supported dependency there:

```bash
python3 -m venv /absolute/private/path/router-venv
/absolute/private/path/router-venv/bin/python -m pip install 'typesafe-sdk==0.7.5'
PYTHON=/absolute/private/path/router-venv/bin/python
```

This downloads a dependency; it is not an offline step. Bind that environment's
Python executable when building the plugin (do not resolve a virtualenv's Python
symlink to its base interpreter, which would lose that environment). Rebuild into
a new output path if the earlier package used another interpreter. The isolated worker ignores user
site packages and `PYTHONPATH`, so installing the SDK somewhere else is not
enough. A wrong SDK version is rejected rather than silently used.

Supply `TYPESAFE_API_KEY` in the actual host process's environment, or build with
`--key-file /absolute/private/path/jev-key.env`. A key file must be a regular,
owner-owned, single-link file with permissions `600`, not a symlink. It contains
one nonempty assignment `TYPESAFE_API_KEY=...` (no shell `export` and no surrounding
shell quotes). Comments beginning with `#` and blank lines are allowed. Do not
put keys in project JSON, argv, screenshots or source control. The builder binds
the key's path but never copies/reads its bytes; the key is loaded lazily only
after the assessment consent gates. No key is supplied by this repository.

## Inspect payloads before sending

```bash
printf '%s' 'Review authentication; API_KEY=example-secret-value' \
  | python3 scripts/router_cli.py preview
```

The preview has `external_calls: 0` and grants no consent. `preflight` without
`--send` is also only a local preview, not a classifier recommendation.
Minimization redacts known credential patterns, drops fenced code and truncates
to 8,192 UTF-8 bytes (input limit 100,000 bytes). It is **best effort**, not a
promise that proprietary details or personal data have been removed. Review the
actual summary; do not transmit data you are not authorized to share. The router
sends a task summary, not a full transcript, to the external Jev service. This
minimizer is not a security boundary against a malicious plugin or host.

Only after deciding to permit a provider request, an explicit preflight can be
requested as follows (the command may make one external classification call):

```bash
printf '%s' 'List the names of three imaginary files: alpha.py, beta.py, gamma.py.' \
  | "$PYTHON" scripts/router_cli.py preflight --send --runtime codex \
      --runtime-binary "$CODEX" --project "$PROJECT" \
      --global-config "$PRIVATE/config.json" \
      --capability-profile "$PRIVATE/profile.json"
```

Use a valid Codex profile from the next section. Add `--key-file` if the key is
not in the process environment. For compatible Claude CLI, use `--runtime claude`
and its binary and omit `--capability-profile`. Preflight never executes the
task, spawns a worker, changes host config or grants new consent. Classification
has a hard enclosing deadline (50–2,500 ms, default 2,500), with no retry.

## Codex: diagnose metadata, then prepare native spawns

These commands invoke the installed Codex runtime's metadata APIs, **not model
inference**. They do not access the Jev key or change trust/host configuration.
Unlike `preview` and `explain`, they require a working compatible native runtime;
"no inference" is not a promise that the host cannot use networked metadata.

```bash
"$PYTHON" scripts/router_cli.py inventory --runtime codex \
  --runtime-binary "$CODEX" --project "$PROJECT"
"$PYTHON" scripts/router_cli.py diagnose --runtime codex \
  --runtime-binary "$CODEX" --project "$PROJECT" \
  --capability-profile "$PRIVATE/profile.json"
```

Inspect `reason_codes`, `missing_desired_targets` and the measured permission
modes. To write the private profile, repeat `diagnose` with `--write-profile`.
This is the only write in this diagnostic step; it does **not** enable routing.
Profiles expire after at most 24 hours and are bound to the binary, project,
implementation and effective hook metadata. Re-diagnose after changes.
`advisory_only` means do not expect automatic rewriting.

Currently the Codex command-hook rewrite is measured only for
`bypassPermissions`. **Do not loosen your permission mode to make routing work**;
keep your security policy and accept native inheritance elsewhere. Unrecognized
hooks/conflicts also prevent automatic rewriting.

In an authorized, compatible `auto_workers` session, SessionStart guidance asks
the orchestrator to call the plugin MCP tool `intelligent_router.prepare_task`
with the native `session_id`, a stable `task_id` per assignment and the original
`task_text`. On success, use the returned opaque `task_name` in native
`collaboration.spawn_agent`, preserve the task text and omit `model` and
`reasoning_effort`. Preparation classifies; it does **not** spawn or run the task.
A scope-bound, expiring, single-use reference carries the decision to the spawn
hook because the native spawn message is not treated as readable plaintext.
Retries reuse the same task ID, never mint a new one to force reassessment.
Missing/expired preparation, changed policy or explicit pins means native
inheritance, not a guessed route. A prepared reference is orchestrator-attested,
not proof that the original task was executed unchanged.

## Claude: final-classic, not a competing command rewrite

Classic hooks observe lifecycle and may advise the root. Automatic worker
routing belongs to the native middleware packaged by `--global-scope`: it awaits
the completed classic `PreToolUse` batch, checks eligibility and only then merges
model/effort into the final `updatedInput`. It preserves permission outcomes and
other fields; an `ask` or `deny` batch is not routed. Explicit pins in either
original input or final batch are preserved. Exact host/companion/module
coverage is required as described in installation. The router never treats an
ordinary command hook's guessed merge order as safe rewrite authority.

## Explain retained decisions offline

No runtime, classifier, credentials or live catalog is consulted, and no state is
modified. Select the exact known session and the correct bound state directory:

```bash
python3 scripts/router_cli.py explain --runtime codex \
  --project "$PROJECT" --session-id 'YOUR_NATIVE_SESSION_ID' \
  --state-dir "$PRIVATE/state" --limit 20
```

Alternatively use `--scope-hash` with a known 64-hex retained scope hash, without
`--project` or `--session-id`. `--row-id` selects an exact retained row;
`--limit` accepts 1–50. In a global-scope installation, use that working
directory's hashed state subdirectory, not the parent state root. It can be
computed locally from the exact working-directory spelling used by the host:

```bash
SCOPED_STATE="$(python3 - "$PRIVATE/state" "$PROJECT" <<'PYTHON'
import sys
from router_core.global_scope import state_path
print(state_path(sys.argv[1], sys.argv[2]))
PYTHON
)"
```

Pass `--state-dir "$SCOPED_STATE"` instead for that installation.
History is bounded, rotating and best effort. `no_records` can mean wrong scope,
no retained state, expiration or logging off; it does not prove zero calls.
A recommendation or `rewrite_emitted` row is **not** proof of the model executed,
task success or savings. Catalog snapshots describe then-recorded availability,
not current entitlement. Do not infer an exact parent-spawn/child-execution join.

## Disable and troubleshoot

- **Emergency stop:** launch the host with `ROUTER_DISABLE=1`. Merely exporting it
  in an unrelated terminal does not update an already running app's environment.
  Also set the bound user config to `mode: disabled` for a persistent stop.
- **No routing:** check mode/consent first, then runtime version, SDK environment,
  private key permissions, actual native hook trust, capability profile and
  exact verified target availability. Never fix this by removing safety gates.
- **`runtime_unverified` / unsupported surface:** there is no compatible adapter;
  native behavior is preserved. A desired model in policy is not runtime proof.
- **`rewrite_evidence_unavailable` / `advisory_only`:** hook conflicts or permission
  semantics are not verified. Review metadata and keep native behavior.
- **`classifier_unavailable`:** missing key/SDK, SDK mismatch, timeout or invalid
  provider output can all defer routing. Errors avoid secret-bearing exception
  text; do not enable raw task/key logging to investigate.
- **Invalid config:** validate with `load_config` above. Project files may revoke,
  not expand, user authority. Do not copy legacy settings into schema 1.
- **Logging:** `observability.log_decisions: false` disables decision telemetry,
  not all state needed for boundary tracking, deduplication and prepared refs.
  Raw prompts are never a supported telemetry option. Preserve private ownership
  and permissions; do not publish state directories as generic debug bundles.

For removal and code rollback, follow [installation](installation.md#disable-uninstall-or-roll-back).

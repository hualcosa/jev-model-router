# Local privacy preview and read-only preflight

These commands do not install hooks, execute the described task, spawn workers,
or change the host's model/configuration. Task text is read from stdin, not argv.

## Inspect locally first

From the repository root:

```sh
printf '%s' 'List the names of three imaginary files: alpha.py, beta.py, gamma.py.' | python3 scripts/router_cli.py preview
```

The JSON shows the exact minimized `task_summary` state, byte count, redactions,
code omission and truncation. No configuration, runtime binary, key or provider
is accessed. `preflight` without `--send` also performs only this local preview.

**Redaction is best effort, not a confidentiality guarantee.** Preview output may
still contain sensitive task content. Inspect it locally; do not publish it or
put it in shared logs. Previewing never grants permission to send anything.

## Explicitly request an assessment

`preflight --send` requests at most one external classification. It still requires
an already-enabled global mode and existing global consent; project config can
only narrow those permissions. `--send` cannot enable either consent flag.
Synthetic-only consent accepts only the exact shipped synthetic fixture above;
arbitrary text does not become synthetic through a CLI switch.

```sh
printf '%s' 'List the names of three imaginary files: alpha.py, beta.py, gamma.py.' | python3 scripts/router_cli.py preflight --send --runtime claude --runtime-binary /opt/homebrew/bin/claude --key-file "$HOME/.config/intelligent-agent-router/jev.env"
```

This example does **not** create or enable config. A disabled/unconfigured router
does not call Jev. An eligible request uses the same minimizer, consent gates,
hard-deadline client and deterministic policy as native adapters. Key access is
lazy, after those gates. `ROUTER_DISABLE=1` prevents sending.

Output contains a recommendation or an explicit skip/defer reason, never a worker
selection or task text. No active root session is required. Low confidence and
missing/unsupported capabilities defer rather than invent a route.

## Current limits and evidence

- Bootstrap catalog is only the exact CLI primitives already measured: Claude
  2.1.303 Haiku/Medium; Codex 0.163.0 Luna/Medium. This is not the full desired
  catalog, nor desktop support. Higher-tier tasks may correctly have no route.
- State-only preview excludes fixed SDK question/schema instructions and private
  authentication headers. It shows the exact task-dependent state, **not** the
  full HTTP wire request; no key is printed.
- This work did not change saved consent or send any new Jev request. Existing
  authorization remains synthetic-only. Real-task opt-in is still separate.
- `tests/test_router_cli.py` exercises CLI wiring with an injected provider,
  secret redaction, bounds, lazy credentials, zero calls without consent, and
  recommendation-only behavior. Existing privacy/policy suites remain applicable.

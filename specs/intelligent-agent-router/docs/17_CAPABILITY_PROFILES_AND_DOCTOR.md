# Private capability profiles and metadata doctor

## Implemented, not installed

The production hook and MCP launchers accept `--capability-profile`. No global
configuration, native trust definitions, or routing opt-in was changed. Without
this explicit trusted launcher argument, conservative bootstrap behavior remains.
Project configuration cannot select a profile or grant rewrite authority.

`router_cli.py diagnose` queries only official Codex app-server metadata
(`initialize`, `model/list`, `hooks/list`). It never reads the provider key or
makes inference calls. `--write-profile` explicitly writes a private profile;
it does **not** install hooks, enable routing, or approve native hook trust.

Example dry run (replace all paths with actual absolute paths):

```sh
python3 scripts/router_cli.py diagnose --runtime codex --surface cli \
  --runtime-binary /absolute/path/to/codex --project /absolute/project \
  --capability-profile /absolute/private-directory/profile.json
```

## Authority and invalidation

- Exact runtime, surface, version, canonical project scope **and lexical source
  spelling**, binary identity, router implementation hash, and effective hooks
  digest are bound together. Profiles expire after at most 24 hours.
- Reads require private owner-only directory/file permissions, no symlink or
  hardlink, bounded strict JSON, and exact schema/catalog validation. Writes are
  atomic and refuse unrelated existing files. No raw hook commands, credentials,
  task content, or free-form catalog evidence are persisted.
- Loader queries current public hook metadata and recomputes conflict safety.
  A JSON boolean cannot grant safety. Changed code, binary, scope, inventory or
  expiry invalidates the profile. Owner-controlled profiles are not a security
  boundary against that same owner.
- Exactly one recognized trusted synchronous production router command must
  match spawn. Unknown/competing/untrusted/async/duplicate hooks disable auto.
  Recognition rejects shell expansion/operators and requires absolute path
  arguments; quoted ordinary paths containing spaces are supported.
- Regex overlap uses actual search semantics only after validation against a
  bounded linear subset. Unknown expressions conservatively overlap. This
  avoids both arbitrary backtracking and treating `spawn.agent` as a literal.
- Long-lived MCP preparation refreshes emergency disable, consent/config and
  profile authority on every request. Keys remain lazy. Cached assessments do
  not trigger another provider call merely because configuration changed.

## Verified scope and remaining gates

Only Codex CLI **0.163.0**, `bypassPermissions`, has measured native rewrite
evidence. This does not grant permissions or alter the user's permission mode.
Claude hook inventory, desktop execution, other modes/versions, production
installation/coexistence, offline decision explanation and rollback remain
unverified or incomplete. This feature alone closes no additional backlog task.

Actual read-only doctor on the original explicitly trusted disposable fixture
returned `advisory_only`: its older spike command is **not** the production
launcher. This is the expected fail-closed result, not positive production
integration evidence. No profile was written. Public inventory lacked Terra6;
this is not an account-entitlement conclusion.

Validation: 565 tests on default Python (2 optional SDK skips); all 565 passed
on the existing SDK0.7.5 interpreter. Profile tests include wildcard/substring/
prefix overlap, unknown pathological regex, shell substitutions/operators,
scope/expiry/code/binary changes and unsafe private files. No payload execution
was used to test shell rejection. See `evidence/p1/capability-profiles.json`.

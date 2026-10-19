# Offline decision explanations — RTE-042

## What ships

`router_core/explain.py` and `scripts/router_cli.py explain` read retained schema-1
telemetry and saved immutable policy/catalog snapshots. They never classify again,
read a key, load current config/profile, launch the host, discover models, read
stdin/transcripts, execute a task or enable routing. This works with missing or
unsupported host binaries and while the router is emergency-disabled.

The existing `diagnose` command remains the **separate explicit live metadata**
inspection/profile tool described in `17_CAPABILITY_PROFILES_AND_DOCTOR.md`.
`explain` is not an alias for it and never silently calls it.

## Usage and scope selection

Choose one explicit selector. Hashes are preferable if you do not want raw native
session identity in shell history. A hash is a selector, not a credential.

```sh
python3 scripts/router_cli.py explain \
  --state-dir "$HOME/.local/state/intelligent-agent-router" \
  --scope-hash 'REPLACE_WITH_64_HEX_SCOPE_HASH' --limit 20
```

Or derive the same hash from explicitly selected runtime, session and project:

```sh
python3 scripts/router_cli.py explain \
  --state-dir "$HOME/.local/state/intelligent-agent-router" \
  --runtime codex --session-id "$NATIVE_SESSION_ID" \
  --project '/absolute/path/to/project'
```

`--project` is required for the runtime/session alternative; explain never silently
selects cwd as the project. It is canonicalized exactly as native state scope.
Other CLI commands retain their existing cwd default. Do not mix explicit
project/session selection with `--scope-hash`. Optional runtime/surface filters
must match recorded rows; they do not validate the current host.

`--row-id` selects one exact 32-hex row **inside** that scope. Otherwise the last
`--limit` retained rows are returned (default 20, range 1–50). The order is stored
publication order, not proof of cross-process causality. Scope hashes and row IDs
are present in returned records; raw session/task/tool/agent IDs are not returned.

`--send`, `--write-profile`, `--runtime-binary`, `--key-file` and
`--capability-profile` are rejected before store construction. `--global-config`
is not read or used by this command; historical configuration comes only from a
matching saved snapshot. There is no outbound consent or credential setup step.

## Output and interpretation

Machine-readable JSON contains:

- Recorded reason plus deterministic explanation, normalized requirements,
  confidence, selected/recommended route, mode, recorded host/version and hashes.
- `policy_provenance` (`policy_prior` for current assessment producers); older
  schema-1 rows without that optional field say `unknown_not_recorded` instead of
  inventing provenance. Unknown provenance inputs sanitize to `unknown`.
- Saved snapshot/policy/catalog hashes, historical policy version and safe typed
  policy controls (threshold, enabled targets/versions, verified-mapping and
  frontier controls). No full config, key/environment/path or free-form evidence
  is dumped.
- Historical matching catalog mappings, supported efforts, mapping status and
  account-availability **source**, never current entitlement. Known source labels
  may be displayed; unrecognized labels and evidence are represented by hashes.
- Requested post-tool arguments separate from available host-reported actual
  fields. `reported_by_host` is not independently verified task success.
  Lifecycle IDs can relate starts/stops; a common scope or adjacent time does
  **not** join a parent tool/decision to a child. No actual field is manufactured
  by the explain layer.

The saved catalog status is `recorded_snapshot`, `missing_or_expired`,
`unavailable` or `hash_mismatch`. Snapshots must match the selected scope and all
snapshot/catalog/policy reference hashes before their metadata is attached.
Multiple possible tool mappings remain `ambiguous`; none is guessed. Metadata
failure does not discard an otherwise valid retained decision or trigger repair,
reclassification, a runtime check or a new provider request.

Exit 0 means the offline read completed: status `explained` or `no_records`.
No records does **not** establish disabled routing, zero prior calls or success.
Unsafe/corrupt telemetry, unavailable lock or invalid selection returns exit 2
and a sanitized error. A corrupt/unavailable snapshot can instead produce an
explained record with metadata `unavailable`. Paths and caught exception prose
are not included in errors.

## Read-only and retention guarantees

The command uses the existing descriptor-anchored owner-private root and 0600
single-link regular files, with a bounded **shared** lock. It never creates a root
or lock, takes a writer transaction, cleans orphan temporaries, prunes state on
disk or rewrites telemetry. Files without their synchronization inode are refused.
Batch snapshot lookup reads bounded state once, filtering expiry only in memory.
Telemetry and snapshots are independent shared-lock reads, joined by content hash,
not an invented common-instant snapshot.

The launcher disables Python bytecode writes before router imports, so even a
fresh relocated package does not acquire an import cache when running explain.
Tests check bytes, modes, inodes, file mtimes and directory mtime; normal read
access/OS atime changes are not a no-I/O guarantee.

Logs rotate by size and are best-effort, not exactly-once/complete history.
Identical crash-rotation row duplicates are deduplicated; conflicting content for
the same row ID is treated as corruption, never arbitrarily selected. Snapshots
expire independently (up to 24 hours) and may be gone while logs remain. Explain
reports that gap rather than fetching current metadata or assuming prior values.
No complete provider totals, quality, cost-saving or quota conclusions are inferred.

## Verification and limitations

- `tests/test_router_explain.py`: **23** tests covering recorded reason/provenance,
  typed saved policy/catalog controls, scope/runtime/row/limit isolation,
  missing/expired/corrupt/hash-mismatched snapshots, legacy provenance, unknown
  catalog labels, ambiguous tools, child non-correlation, conflicting row IDs,
  unsafe files/locks, no temp cleanup or writes, explicit CLI guards,
  missing-project rejection before store construction and concurrent writers.
- Guarded CLI tests fail on config/key/runtime/profile/inventory/provider or stdin
  access. Relocated packaged CLI test checks no state/cache/file mutations.
- `explain-offline-native-format.json`: a real Python CLI subprocess, run from
  outside the checkout with DEVNULL stdin and provider credentials removed,
  explains one seeded native-format core shadow assessment. State
  bytes/modes/inodes/mtimes remain unchanged. Seed classifier is deterministic,
  **not Jev**; no native host or provider calls occur in this smoke.
- Full suite: **658** pass. Default interpreter has two expected optional SDK skips;
  pinned typesafe-sdk 0.7.5 interpreter has no skips.
- Independent source review found one medium implicit-project-selection issue;
  fixed and rechecked, no residual finding in that guard. Other reviewed offline
  paths had no medium/high findings. Duplicate-ID and import-cache hardening have
  focused regression coverage; this is not a release-wide security certification.
- `codex-package-explain-native.json`: current payload version
  `0.1.0+509f801aea42` passed isolated native Codex 0.163.0
  install/list/doctor/disable/uninstall/marketplace removal; eight hooks discovered,
  all untrusted, no provider/inference calls or principal config changes.

This closes the offline diagnostic/explain task, not the entire release. Claude
cold-root metadata, trusted packaged execution, desktop, full permission/conflict
matrix, representative task-quality benchmarks and overhead remain separate gates.
No principal/global router activation, trust mutation, commit or push was made.

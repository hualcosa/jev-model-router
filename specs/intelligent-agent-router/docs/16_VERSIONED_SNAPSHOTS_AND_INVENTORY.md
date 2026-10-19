# Versioned decisions and public capability inventory

## Decision snapshot contract (RTE-017)

Every `assess`/`decide` result carries:

- `version`: the semantic policy code version;
- `catalog_version`: SHA256 of canonical catalog metadata;
- `snapshot_version`: SHA256 binding policy version + effective configuration +
  that catalog version.

The independent snapshot schema is version 1. Canonical JSON and sorted catalog
entries make identity stable across dictionary/registry ordering. Returned
objects cannot mutate the stored snapshot. Configuration has no key value field;
catalog snapshots persist only bounded labels and SHA256 of free-form evidence,
not evidence prose, task text, raw responses or credentials.

Native Claude and Codex preparation persist the scoped snapshot **before** a
provider callback. It uses the same 0700/0600 transactional, bounded private store,
including locking, ownership checks and TTL/count/byte limits. Snapshots retain
24 hours, at least the maximum decision/prepared-reference lifetime. Capacity or
unsafe-state failures defer rather than create an unauditable route.

Historical decision JSON without the two new optional fields still roundtrips
exactly, including existing private-state records. It is not silently upgraded.
Current native rewrites require an exact current policy/snapshot/catalog match;
older decisions remain readable but cannot act as current routing authority.
Ranking/floor/decision-algorithm changes must bump the semantic policy version;
configuration and catalog changes independently change their content hashes.
Preflight stays read-only: its JSON includes the snapshot for optional caller
retention instead of implicitly writing state.

Tests: `tests/test_core_snapshots.py` and native adapter regressions cover stable
hashes, config/version/catalog changes, sanitized evidence, strict decoding,
scoped persistence/expiry, old-record decoding, durable-before-provider ordering,
and stale cache abstention without a duplicate classification.

## Public Codex inventory

```sh
python3 scripts/router_cli.py inventory --runtime codex --runtime-binary /opt/homebrew/bin/codex
```

This read-only command uses the documented app-server handshake and `model/list`
with bounded cursor pagination. It sends no thread/turn/inference methods, task,
Jev request or credential values. Process groups are deadline-bounded/reaped;
server stderr/error prose is not printed. The runtime version must match the
verified native spawn-field profile. It does not install or activate routing.

Exact numeric slugs are matched to the requested target generations; aliases and
display names are not version evidence. Model-specific advertised effort options
are retained independently of the default. Unknown/ambiguous IDs, unsupported
efforts and duplicate mappings fail safely. Availability stays `user_assumption`,
not a claim that inference has verified account access. Public metadata is also
not a claim of live spawn proof for every model/effort combination.

Current observed CLI 0.163.0 output is captured in
`../evidence/p1/codex-public-inventory.json`: Luna 6, Sol 6.1 and Astra 6 match.
Terra 6 is **not advertised**, even including hidden entries; Terra 5.6 is
advertised but intentionally excluded. This is not an entitlement verdict and
does not authorize changing the requested generation.

The current bootstrap remains partial/gated until the production profile loader,
permission/conflict diagnostics and live matrix are implemented. Claude CLI has
no demonstrated public machine-readable equivalent here, and desktop requires
its own evidence. No private runtime cache/transcript is used for discovery.

Sources: [official app-server protocol and model/list](https://learn.chatgpt.com/docs/app-server),
[Claude model configuration](https://code.claude.com/docs/en/model-config).

`tests/test_core_inventory.py` exercises fake protocol workers, pagination,
deadline/cleanup, exact generations, effort validation, malformed output and
version mismatch without inference. The captured public inventory is separately
observed evidence, not a substitute for those fault tests or the live matrix.

## Concurrency verification follow-up

The full pinned-SDK suite exposed an intermittent first-use lock publication
failure (11 of 12 distinct callbacks). Sanitized diagnostics reproduced ENOENT
at the concurrent lock `open(O_CREAT|O_NOFOLLOW|O_NONBLOCK)`, before classification.
Publication now uses exclusive creation followed by open-existing without create.
A disappeared existing lock is never recreated, to avoid splitting synchronization
between inodes. Twenty 12-process repetitions passed after the fix, plus two
deterministic regressions. Final default and pinned-SDK suites both passed 546
tests (default skips two optional-SDK cases). The earlier failed run is retained
in `versioned-snapshots.json`, not silently treated as a pass.

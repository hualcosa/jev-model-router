# Codex production-core composition evidence

`../evidence/p1/codex-core-native.json` records a passing official **Codex CLI
0.163.0** synthetic run. This is the shared implementation, not the static P0
rewrite: `PreparationService` → stdio `MCPServer` → privacy/consent → deterministic
policy → `PrivateStateStore` single-use reference → `NativeAdapter` spawn rewrite.

## Observed in one terminally successful run

- Exactly one plaintext preparation and one injected deterministic classification.
- Exactly one native spawn, originally without model/effort pins.
- Native message remained opaque; no decoding or private transcript access by
  the production router. The generated preparation reference matched task_name.
- Original nonrouting arguments matched the native post-hook arguments.
- Actual child model was `gpt-6-luna`, effort `medium`; principal remained
  `gpt-6.1-sol`, effort `low`.
- Parent and child retained `read-only` sandbox and `never` approval policy.
- Zero Jev calls or key access. No global config changes or native trust bypass.
- Existing scratch hook/MCP scripts restored, including original permissions.

Model evidence includes official native `SubagentStart`/`SubagentStop` fields.
Effort and permission evidence comes from **test-only synthetic host turn_context**
records supplied through the native hook paths. This verifier is a spike, not a
production transcript API or a proposal to depend on that format at runtime.

Pins/custom profiles are separately tested as zero-call/no-mutation native-format
fixtures in `tests/test_native_adapter.py`. A broad live pins/permissions/conflict
matrix remains separate work; one passing unpinned route does not establish it.

## Approval and path discoveries

The production MCP tool truthfully declares state-changing/open-world annotations:
it can write local state and, with independent consent, call Jev. The host rejected
the first real call because it required approval while approval_policy was never.
After explicit user authorization, the smoke added only the invocation-local
`mcp_servers.router_synthetic_p0.tools.prepare_task.approval_mode="approve"`
override. It did not mislabel the tool as read-only or alter persisted permissions.
See [official MCP configuration](https://learn.chatgpt.com/docs/extend/mcp).

On macOS, resolving the reviewed `/var/...` scratch spelling into `/private/var/...`
changed the native hook source identity. No session was registered, so preparation
correctly deferred. Keeping the originally reviewed `-C` spelling restored the
existing trusted hooks, without copying trust hashes. The adapter still uses
canonical filesystem paths for isolation. See [official hook trust documentation](https://learn.chatgpt.com/docs/hooks).

## Reproduction and limits

`scripts/spikes/codex_route_smoke.py --help` describes the explicit opt-in. Supply
`--run-synthetic --workspace <already-reviewed-disposable-fixture>` and optionally
`--output <report.json>`. It expects the original fixture's six command hooks and
`router_synthetic_p0` MCP registration; it does **not** install or trust them.
New/changed native hook review must still be completed through the native UI.

The runner preserves the fixture files, disables unrelated user MCP servers for
this invocation, and retains private synthetic diagnostic artifacts. It does not
use `--dangerously-bypass-hook-trust`. Its bounded timeout terminates the process
group; verifier/restoration tests run without inference.

**Not established:** live Jev-to-native selection, desktop, full desired catalog,
on-request approvals/denials, competing hook ordering, cryptographic equality of
prepared plaintext and opaque task, or general root compliance with preparation.
Default production capability profiles remain gated, not globally activated.

## Live Jev composition (additional evidence)

`../evidence/p1/codex-live-jev-native.json` is a separate passing run through the
real SDK0.7.5 and public model-list catalog, with versioned snapshots enabled.
Exactly one Jev call classified shipped synthetic `TASK-011` as T1/low risk,
confidence **0.83**, in **471.07 ms**. The unchanged 0.75 threshold accepted it.
The policy selected an actual Sol6.1/Medium child; principal stayed Sol6.1/Low,
with read-only sandbox and never approval preserved. No injected classifier or
forced fallback was used for this run.

Reproduce with the existing explicit synthetic flag plus `--live-jev
--sdk-python <absolute-interpreter-with-pinned-SDK0.7.5>`. The private key loader
reads the external configured Jev key file; no key is passed in argv or logged.
Low confidence or provider failure must still defer—do not lower the threshold
to make a reproduction pass.

This verifies the provider → policy → preparation → native chain for **one
synthetic task**, not general classifier quality or actual task implementation.
The worker was prohibited from modifying files. The earlier eight-task live
sample (`../evidence/p1/jev-synthetic-sample.json`) had only one result meeting the
threshold and both expected-T3 tasks below T3; it is not an outcome benchmark.
Desktop, permissions/coexistence matrix and the full desired catalog remain open.

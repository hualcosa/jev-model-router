# Root-only capability-gap advisory

## Core behavior

`NativeAdapter` gates root assessment through the persisted boundary machine,
builds an envelope from trusted observed root metadata, and classifies only a new
logical task. At most one assessment is claimed before the provider callback.
Worker/internal events, clear continuations and acknowledgments do not trigger
another root assessment. Disabled/warnings-off/no-consent paths do not call Jev;
shadow may assess but never emits a warning or mutation.

Policy compares the eligible recommended route against a verified current route.
An adequate/higher current model, unknown current route/effort where required,
unsupported candidate, low confidence or provider failure produces no warning.
The material-gap rule is an ordinal **policy prior**, not measured quality,
latency, savings or subscription-quota evidence. Same-model effort advice and a
model-change recommendation are explicitly distinguished.

`router_core/advisory.py` includes current/target route, delta rationale,
classifier confidence, uncertainty, manual controls and preflight guidance.
Warnings truthfully say they occur **during submission**, are nonblocking, and
do not pause execution. Only bounded route labels enter the message, never raw
prompt/provider prose. Output contains only `systemMessage` plus supported
`additionalContext`, not approval/block/config/model mutation fields.

The warning delivery claim atomically checks the expected logical task **and**
root observation. A slow classification finishing after a manual model switch,
new task or compaction cannot deliver stale advice or consume its fingerprint.
Duplicate concurrent hooks produce at most one warning per task/recommendation.
Boundary transition/reset and its model observation are also one transaction;
late duplicates cannot revert a newer model observation. A known duplicate's
older clock sample is not treated as fresh evidence of clock regression.

## Native Codex evidence and presentation differences

`evidence/p1/codex-root-advisory-app-server.json` records a successful actual
Codex **0.163.0** app-server turn against the original reviewed disposable hook.
Exactly one injected deterministic classification of the shipped imaginary-file
task produced one native root warning. Official `hook/completed` for
`userPromptSubmit`, status `completed`, contained an exact matching `warning`
entry. Root metadata remained `gpt-6-luna` at SessionStart/submission; only
advisory output was emitted. No Jev call, hook-definition/trust/global-config
change, binary patch or transcript parser was involved.

This is shared-core/real-host integration evidence, **not** a production launcher
installation or live-Jev root-advice proof. The prior separate worker live-Jev
proof does not fill that gap. The smoke retains private synthetic artifacts and
restores fixture script content/permissions on exit.

Keep the negative evidence:

- `codex-root-advisory-native.json`: `exec --json` completed and the hook emitted
  one warning, but this run did not expose it in stdout/stderr. Emission alone
  was correctly not accepted as warning visibility.
- `codex-root-advisory-tui-bootstrap-failure.json`: historical terminal bootstrap
  failed loading workspace requirements, before hooks. Original raw logs and the
  empty event list remain available; this was not an established account issue.
- `codex-root-advisory-tui.json`: a later **actual TUI rendering check passed**
  after replacing partial MCP overrides with invocation-only `mcp_servers={}`.
  The terminal contained the native `↳ Hook · Router advisory...` presentation,
  not merely a model-context echo. Exactly one classification/warning, exit0,
  no forced termination or auth/global-config/trust changes. The smoke exits
  after warning rendering and does not establish interactive model-task completion.
- Desktop remains unverified, as does execution from an installed/trusted
  production package. A fixture TUI check does not fill those separate gates.
- No root effort field was observed at these native root boundaries. Do not
  infer active effort from desired CLI/config values. Effort-only warnings
  require an authoritative observation; otherwise they abstain.

The [official hook reference](https://learn.chatgpt.com/docs/hooks) documents
`model`, prompt `turn_id`, and `systemMessage` versus model-context semantics.
The [app-server reference](https://learn.chatgpt.com/docs/app-server) documents
hook lifecycle notifications. Installed-version generated schema confirmed
`HookRunSummary.entries[{kind,text}]`, with `warning` as a kind. The installed
API accepted sandbox `read-only`, not the camel-case example from current prose.

## Reproduction and tests

```sh
python3 scripts/spikes/root_advisory_smoke.py --run-synthetic --app-server \
  --workspace /absolute/originally-reviewed-disposable-project \
  --output /absolute/report.json
```

Omit `--app-server` to reproduce the separate exec-JSON visibility check; use
`--tui` for the independent real-terminal check. Each requires the explicit
synthetic flag and consumes official Codex usage. No trust bypass is supported.
App-server's production metadata client still forbids thread/turn methods; the
explicit inference runner is separate test-only code.

Eight root presentation/lifecycle tests cover effort-vs-model rationale, unsafe
labels, eight-thread dedupe, continuations, unknown/equal/better routes, shadow,
disabled, provider failure, low confidence and concurrent stale-state changes.
Six spike tests reject context echoes, missing native identity and unexpected
control fields, and exercise cleanup with a TERM-ignoring child retaining stdout
after its parent exits. The root checkpoint's full suite was 579 tests OK on
SDK0.7.5; later package work adds tests recorded separately. Production
installation, Claude native advisory, full CLI/
desktop matrix and release gates remain separate backlog work.

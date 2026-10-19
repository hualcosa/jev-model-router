# Claude observations and cold-root limitation

## RTE-028: implemented available truth

The shared adapter consumes documented CLI 2.1.303 lifecycle and model-switch
fields without reading transcripts or requesting another classification:

- PostToolUse records Agent argument model/effort as **arguments**, not actual.
- SubagentStart/Stop carry a scoped hashed agent identity; stop `effort.level`
  is recorded as **reported_by_host** when present. Child model remains unknown.
- Start/stop can be matched to each other by agent identity within one scope.
  No parent-tool-to-agent join is inferred, including for concurrent workers.
- PostModelSwitch records `to_model` as host-reported; actual effort stays unknown
  in telemetry. The root state is refreshed without applying a switch itself.
- Missing fields remain unknown, not inferred from a requested pin, configuration,
  previous root, aggregate model usage, or a custom agent's name.

`../evidence/p1/claude-telemetry-native.json` is an actual isolated native run:
root Sonnet/High, one generic unpinned Haiku/Medium worker through shared core,
policy and private state; one deterministic callback, no external Jev call;
nine parsable telemetry records including one assessment, one PostToolUse, and
one matching child start/stop. Native aggregate model usage plus independent
root AssistantMessage proves the controlled fixture used Sonnet and Haiku.
The production child record nevertheless keeps model **unverified**, effort
**reported_by_host**, and parent-tool correlation **unverified**.

Manual-switch **native-format unit fixtures**, not a live manual-switch test,
verify canonical root-model refresh, unknown effort, policy matching and truthful
PostModelSwitch telemetry. Live manual switching, concurrency/coexistence,
permissions matrices, packaged execution and desktop remain RTE-029/047 and
related release gates. Completion of RTE-028 does not complete those tasks.

## Exact observed IDs are not executable worker IDs

The root matcher previously required `runtime_model_id == observed model`.
Claude uses different namespaces: native Agent accepts `haiku`, while actual
model reports identify `claude-haiku-5-5`. Replacing the executable alias with an
observed model ID would assert an untested Agent input and is not the fix.

Catalog schema 1 now accepts optional `root_model_ids`: an immutable, bounded
list of **explicit verified observational identities**, used only for root advice.
It is omitted when empty (historical JSON remains unchanged), validated on load,
and included in policy/catalog snapshot hashes when present. No family prefix,
version pattern, moving alias expansion or unverified mapping is guessed. Root
matching uses exact verified mappings in the current runtime/surface/host/tool
scope. Ambiguous identities defer. Same-capability effort advice preserves the
observed canonical label and does not misleadingly call it a model change.
Worker mutations still use only `runtime_model_id` and verified native fields.

- Haiku: executable alias `haiku`, observed `claude-haiku-5-5`, Medium proven.
- Sonnet: executable alias `sonnet`, observed `claude-sonnet-5-5`, **only Medium**
  added after a new isolated static primitive probe. Parent actual Opus/High,
  exactly one generic Sonnet/Medium child, nonrouting arguments unchanged,
  native result with both models and positive output-token counts, no approval
  decision emitted. See `../evidence/p1/claude-sonnet-alias-native.json`.
- Opus as a test **root** is not proof of Opus as a worker. No Opus/Fable worker
  mapping or additional effort level was inferred from these tests.

The controlled primitive verifier now requires independent official root
AssistantMessage metadata (explicit null `parent_tool_use_id`), same native
session across hooks/root messages/result, exact expected model aggregate and
positive output tokens. A present contradictory SessionStart model fails even
if all aggregate models are present. Aggregate-only evidence cannot establish
root/child attribution. These checks strengthen reproducibility, not general
per-child model attribution.

## RTE-024: interactive advisory verified; print-mode limitation remains

Actual native root-only evidence is in
`../evidence/p1/claude-root-native-capability.json`:

- CLI 2.1.303 **in `-p` print mode omits SessionStart.model**, although current docs describe it as
  optional. Actual UserPromptSubmit **does include prompt_id**.
- One new synthetic root task invokes exactly one deterministic classification;
  the policy then defers `active_route_unknown`. There is no warning and no
  root mutation output. Native Stop reports Medium and the public root assistant
  message independently reports Haiku 5.5.
- The public assistant message arrives **after** the submission; it is used only
  by the test verifier. It does not supply model metadata to a production command
  hook before the task. No transcript parser, stream proxy, hidden bridge or
  configuration-based model assumption was added to hide this limitation.

That is **not** evidence that the interactive CLI lacks the field. A subsequent
real TUI run on the same 2.1.303 version supplied `SessionStart.model` before the
first submission. Existing shared-core code then displayed the nonblocking
Sonnet/Medium recommendation from Haiku 5.5, completed the response, and treated
the following `sim` as continuation: one classification and one warning across
two completed turns. Official status-line observations independently reported
Haiku 5.5/Medium before and after; native Stop reported Medium twice. No root
mutation, production transcript parser or status-line bridge was introduced.
Status line was test-only corroboration; the production hook used SessionStart.

See `../evidence/p1/claude-root-interactive-native.json`. RTE-024 shared-core
interactive advisory acceptance is met; packaging remains RTE-027. The initial
generalization from print mode to all CLI sessions was incorrect. Print mode
still fails open without advice when model metadata is absent; desktop and
same-model effort upgrades before the first effort observation remain unverified.
Explicit preflight is not represented as a replacement for either missing path.

## Verification

- Seven root identity/catalog/policy tests cover exact aliases, malformed and
  mutable lists, snapshot binding, same-model effort, ambiguity, model switches
  and continuation suppression; additional switch telemetry assertions included.
- Native-verifier mutation tests reject contradictory roots, mixed sessions,
  missing/nested-only root-message identity, zero child usage, different lifecycle
  agents/scopes and invented actual fields. Root-capability verifier treats
  missing hooks as degraded, not successful advice; blocking/mutation outputs,
  invented warnings and mixed sessions fail.
- Full pinned typesafe-sdk 0.7.5 suite: 634 tests pass, no skips. Default interpreter
  also has the same suite with two expected optional SDK skips (record latest run
  in the evidence file).
- Independent source review found two medium evidence-verifier flaws, both fixed
  and rechecked with focused tests and fresh native probes. No remaining concrete
  medium/high finding in the reviewed root identity or verifier controls.

No global hook/plugin installation, trust changes, private project transmission
to Jev, commits or pushes were performed. All new code is in local main's working
copy. Model-token counts are fixture reports, not quality, cost-saving or quota
claims.

Primary runtime contracts:
- https://code.claude.com/docs/en/hooks
- https://code.claude.com/docs/en/agent-sdk/subagents#detect-subagent-invocation

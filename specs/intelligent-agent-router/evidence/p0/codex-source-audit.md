# Native Codex feasibility: verified mechanics and remaining bridge

## Installed and actually tested

Standalone CLI 0.163.0. Desktop ChatGPT.app (bundle com.openai.codex) embeds 0.163.0-alpha.10.2. Do not infer behavior parity. Actual standalone hook tool name was `collaborationspawn_agent`; `spawn_agent`/`Agent` aliases alone would miss this host. Parent SessionStart/UserPromptSubmit/PreToolUse include root model. Worker lifecycle includes model, not effort.

The first fixture used a hyphenated task name; native spawn rejected it without creating a child. Corrected underscore task name succeeded. The synthetic-only hook preserved the original opaque message and other fields, adding only model/effort. Child lifecycle reports Luna; last host-applied settings/turn context report Luna/Medium, parent Sol6.1/Low. Both inherited read-only sandbox/on-request approvals; actual child response exactly matched synthetic marker. See `codex-cli-spike.json`. These prove routing mechanics, not complete security semantics or Jev classification.

Trust was granted only after the user's explicit approval, using native folder trust and hook review for six handlers of the same exact disposable script. No trust bypass, modified binary, copied auth, global router installation or inference proxy. Native trust persistence is expected; disposable script has an exact canonical cwd guard and a single exact synthetic task-name guard.

## Source-supported limitation

Exact desktop source tag (independent evidence, not a claim this source was the standalone executable):

- https://github.com/openai/codex/blob/rust-v0.163.0-alpha.10.2/codex-rs/core/src/tools/handlers/multi_agents_spec.rs — V2 marks message schema encrypted, leaves task_name ordinary, makes model/effort exposure conditional.
- https://github.com/openai/codex/blob/rust-v0.163.0-alpha.10.2/codex-rs/hooks/src/events/pre_tool_use.rs — hook serializes tool_input verbatim.
- https://github.com/openai/codex/blob/rust-v0.163.0-alpha.10.2/codex-rs/core/src/tools/router.rs — native handling of encrypted function arguments; hook cannot claim access to plaintext.
- https://github.com/openai/codex/blob/rust-v0.163.0-alpha.10.2/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs — resolved config snapshot and child route metadata.

Actual standalone smoke independently confirms worker message opaque at PreToolUse while root prompt and child response remain plaintext. No ciphertext is reproduced in this report, decrypted, or sent to an external service.

## Selected mechanism after composition proof

Direct native hooks remain preferred where assignment text is available (Claude, compatible Codex surfaces). For encrypted Codex messages, test a local read-only preparation MCP tool with ordinary non-encrypted input schema before native spawn, and a one-time decision reference in the ordinary task_name. The root supplies task text, not a model/effort choice; native hook applies the core's recorded decision only to an eligible unpinned spawn. If preparation is omitted/expired/uncertain, preserve native input. Static task-name-to-model guesses are NOT equivalent to task-aware classification.

This hybrid adds a tool round trip and depends on orchestration guidance. A decision reference cannot cryptographically attest equality between prepared plaintext and an opaque native task message; label binding honestly as orchestrator-attested, scope/expire/consume references, never call it verified payload-hash binding. Routing is an optimization, not an authorization or content-policy enforcement boundary. Explicit pins, custom profiles, sandbox/approvals and third-party opt-in remain authoritative.

The third synthetic exec probe completed successfully with normal config and per-invocation local MCP registration. Strict same-session assertions establish one plaintext preparation followed by one native hook-routed spawn and actual Luna/Medium child, with root Sol6.1/Low unchanged. See `codex-hybrid-spike.json`. Unlike the earlier TUI, this exec used never approvals/read-only (hook permission_mode bypassPermissions); do not conflate permission-mode evidence. The fixture uses a static synthetic task name, NOT production TTL/replay/session controls. An earlier --ignore-user-config probe loaded MCP but no project hooks and is excluded as composition evidence. ADR-006 records the selected design and pending release gates.

# 03 — Runtime Adapters & Capability Verification

> This is an engineering hypothesis/evidence matrix, **not** a claim that the feature has already been implemented or tested on the user's machine. Always verify against `claude --version`, `codex --version`, the native tool schema and actual host execution.

## 1. Official documentation facts

| Primitive | Claude Code | Codex | Implementation consequence |
|---|---|---|---|
| `UserPromptSubmit` event | Documented | Documented | Cheap root boundary gate; optional warning |
| `PreToolUse` | Documented | Documented for local function tools | Primary subagent routing hook |
| Tool input rewrite | `hookSpecificOutput.updatedInput` documented | Same, with `permissionDecision:"allow"` for rewrite | Use versioned per-host JSON fixtures; test trust/permissions |
| Subagent creation hook | `SubagentStart` | `SubagentStart` | Observability, not sufficient for pre-spawn model choice |
| Agent tool | `Agent`/legacy `Task` in upstream hook | `spawn_agent` matches `Agent` alias | Match only verified names + schema |
| Explicit task lifecycle | `TaskCreated`/`TaskCompleted` documented | Consult actual runtime events / `update_plan` tool only; **not equivalent by default** | Boundary hints are runtime-specific |
| Root model metadata | Common input has model field; model-switch events available | Common input `model`: active model slug | Refresh observed model on session events |
| Root effort metadata | Verify actual input/API | Verify actual input/config; `model` field alone != effort | Do not invent active effort; show “unknown” |
| Subagent model mutation | Supported pattern in existing hook | Supported general local-function rewrite, reference repo exists | Smoke-test actual executed model |
| Subagent effort mutation | **Not assumed** — inspect Agent/Task schema and agent definitions | Exists in community `spawn_agent` router; verify installed schema | Soft capability flag; never inject unsupported field |
| Hook trust | Usual CLI plugin/settings lifecycle | Non-managed hooks require user review/trust | Diagnose untrusted installation, don't bypass it |
| Effect of `permissionDecision: allow` | Inspect and test | Required for `updatedInput`, may permit spawn | Carefully scope only the agent tool |

## 2. Claude Code adapter design

### Upstream fork mapping

Repository: https://github.com/tzachbon/claude-model-router-hook

Current public docs describe a Python router and hook entrypoints:

- `plugins/claude-model-router-hook/hooks/user_prompt_submit.py`
- `plugins/claude-model-router-hook/hooks/pre_tool_use.py`
- `plugins/claude-model-router-hook/hooks/post_tool_use.py`
- `plugins/claude-model-router-hook/hooks/session_init.py`
- `plugins/claude-model-router-hook/hooks/router/` (package directory)

The base plugin presently uses local heuristics with optional `claude -p` fallback, routes `Agent`/`Task` spawns, and warns by default. It may ship routed agent variants and has logic for explicit model overrides. Audit before changing: preserve compatibility, plugin manifest and uninstall semantics, and avoid regressing its operational guards. Disable its optional parent autoswitch in our fork.

### Hook contract to verify

```json
{
  "tool_name": "Agent",
  "tool_input": {
    "description": "Inspect test coverage",
    "prompt": "Find weak spots in unit tests"
  }
}
```

Proposed *output shape* only; valid keys must be checked against installed version:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "updatedInput": {
      "description": "Inspect test coverage",
      "prompt": "Find weak spots in unit tests",
      "model": "<actual-catalog-model>"
    }
  }
}
```

Do not assume an `effort` or `reasoning_effort` key exists on Claude Agent. If unavailable, either leave worker effort inherited, use supported predeclared agent profiles, or document that dynamic worker effort is unsupported in the first version. Do **not** declare the entire two-runtime project done based solely on a claimed effort override.

### Root warning and cache hints

At a root `UserPromptSubmit`, if the boundary gate identifies a fresh new task, issue the appropriate (nonblocking) supported message. `PreModelSwitch`/`PostModelSwitch` documented events can observe manual transitions; `PreModelSwitch` reports `context_tokens`, `prompt_cache_warm`, `cache_ttl` and model names. These are useful **at a switch**; do not imply a prior arbitrary warning can access the same cache metadata. Do not disable/rewrite native `/model` behavior. Never write a future model to settings as the old autoswitch mode does.

### Claude smoke matrix

- Existing Claude Code remains official (`command -v claude`, version before/after).
- Root session Sonnet => remains Sonnet after complex warning; root Opus => remains Opus.
- Spawn generic `Agent` unpinned => observed actual model matches request; explicit model remains untouched.
- Named/custom agent => preserve override/profile policy.
- Non-Agent `Bash`, `Edit`, `Read`, MCP tools => no rewrite or Jev call.
- Multiple workers concurrently => independent records.
- Resume/compact/model switch => refreshed observed root model, no global routing flip.
- Test conflict with other `PreToolUse` hooks rewriting same tool; order is not assumed.
- Verify any official auto permission prompts still behave correctly for all unrelated tools.

## 3. Codex adapter design

### Official hook support

Source: https://learn.chatgpt.com/docs/hooks

- Native hooks support `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `SubagentStart`, `SubagentStop` and other lifecycle events.
- `PreToolUse` covers local function tools, including `spawn_agent` with `Agent` matcher alias. Hosted tools can be excluded.
- `hookSpecificOutput.updatedInput` can replace the argument object of a local function tool; Codex requires `permissionDecision: "allow"` in the same response.
- Active model appears as `model` in the common input fields. **This does not automatically establish active reasoning effort.**
- Non-managed plugin hooks require trust approval; package with a Codex plugin according to the currently documented manifest/hook location.

### Existing reference implementations

- https://github.com/guilhem/codex-subagent-router — a real Jev-based Codex subagent router. Reads JSON task profiles, sends task descriptions to TypeSafe as a `Choice`, and writes selected `model` + `reasoning_effort` into an unpinned `spawn_agent` (according to its README). All explicit pins bypass routing. Use its design as *a reference*, not a compulsory dependency or proof of support on every release.
- https://github.com/hooyao/codex-model-router — Codex plugin MVP with hooks, workspace policy, and init flow. Treat as another reference after checking its license/version.

**Avoid building a second independent model-selection policy.** Reuse one shared core; Codex has only a small host-specific JSON adapter and installer.

### Codex candidate event

```json
{
  "tool_name": "spawn_agent",
  "tool_input": {
    "message": "Inspect and summarize failing tests"
  }
}
```

A valid local rewrite might preserve original keys and add `model` and `reasoning_effort`; verify these fields against the **real** tool schema and available catalog before emitting. Some spawns may use `items` instead of `message`: preserve and validate content type. Skip non-text or multimodal cases until safely supported. If `model` or `reasoning_effort` is non-null, bypass routing before classification. A verified generic default `agent_type` alone is eligible; custom or unknown types bypass. Do not infer pin provenance or strip pins. Generic delegations should omit model/effort at source so the router can choose them.

### Codex plugin packaging

- Determine whether the current installed Codex uses `plugin.json` with `extensions.com.openai` or the compatibility `.codex-plugin/plugin.json` structure; follow official `https://developers.openai.com/plugins/build/plugins`.
- Bundle one `hooks/hooks.json` with command hooks; register exact Python executable or a portable launcher. Respect `PLUGIN_ROOT`, `PLUGIN_DATA` and installer behavior.
- Require review/trust in `/hooks`. Do not claim automatic trust.
- Provide project-level override file and `ROUTER_DISABLE` emergency rollback switch.

### Codex smoke matrix

- `codex --version` and signed-in authentication unchanged.
- `UserPromptSubmit` warning visible for fresh task but no model/effort mutation to main session.
- `spawn_agent` with no pin → verified actual worker model and effort; pinned fields bypass.
- Invalid model, unsupported effort → native spawn defaults; never crashes.
- Check whether `spawn_agent` is intercepted for the actual installed mode/surface (CLI/desktop/web may differ).
- Run `codex` through standard invocation, not `jev-codex` proxy.
- Confirm approval/sandbox do not loosen for other calls.

## 4. Minimum end-to-end smoke protocol (both)

**Required surface matrix:** run this protocol in CLI and local desktop code sessions for each runtime. Shared implementation is preferred; shared-harness assumptions do not replace actual surface evidence. Target account availability is accepted as `user_assumption`; exact IDs/version and effort/schema support remain technical checks. Do not print credentials while diagnosing GUI versus shell environments.


1. Record `command -v`, version, host mode, plugin list, current auth and model catalog evidence (no secrets).
2. Run a baseline session with the router disabled; record root model and a generic child spawn.
3. Enable `shadow`; confirm events and decision records but **zero** input rewrites.
4. Enable `auto_workers` for one explicit unpinned child spawn; inspect hook input and output **plus actual executed model/effort** using host-visible evidence.
5. Repeat with explicit pin, timeout, unsupported model, high-risk task and a concurrently spawned worker.
6. Verify root model/effort remain constant and the CLI continues to function normally.
7. Uninstall/disable the router; confirm baseline behavior is restored without modifying `claude`/`codex` installation.

### Adapter capability statuses

For each tested version capture `supported / unsupported / unknown` and one evidence artifact per claim:

- `observes_root_model`
- `observes_root_effort`
- `warns_root`
- `rewrites_subagent_model`
- `rewrites_subagent_effort`
- `verifies_actual_subagent_model`
- `verifies_actual_subagent_effort`
- `preserves_child_approval_semantics`

Do not promote a capability from unknown to supported based on documentation of a **different surface** or of a **third-party repo** alone.

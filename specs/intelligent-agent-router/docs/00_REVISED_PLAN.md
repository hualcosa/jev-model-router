# 00 — Revised Delivery Plan

## Decision summary

Build **one shared routing core + two first-class runtime adapters**, beginning from a fork of the MIT-licensed `tzachbon/claude-model-router-hook`. Preserve the officially installed `claude` and `codex` binaries and their existing auth and permissions. Use native lifecycle hooks wherever supported. Jev is a **task-assessment component**; a separate benchmark-informed policy chooses a particular model/effort pair from the **actual** runtime catalog. The root model and effort are **advisory-only** and NEVER automatically changed.

A **task boundary** (not every message) is the intended decision unit. Use structural hook events as the strong signal; use a cheap stateful prompt gate and optional explicit preflight for root work. Do not call Jev repeatedly on tool-loop continuations or ordinary follow-ups. Avoid unsupported model/effort mutation and hidden proxies.

## Scope / non-scope

**V1 IN:** root capability warnings for detected new tasks; root model/effort preservation; per-eligible-spawn subagent model routing; Codex effort selection where supported; shared Jev classifier, policy, registry, state, logging, local tests, smoke tests, config, rollback and docs. **Both runtimes get executable adapters in V1.**

**V1 OUT:** auto-switching the root model/effort; global routing through HTTP inference proxy; substituting a modified CLI; pricing claims derived solely from subscription plans; autonomous spawning/decomposition; semantic inspection of private chain-of-thought; automatic task migration between provider accounts; automatic Jev routing for every root prompt; claims of dynamic Claude subagent effort if unsupported by the live tool schema.

## Required semantics

1. The **root** is the model/effort that the runtime reports as active when a session or task runs (not hardcoded Opus). A new root task may generate a nonblocking, once-per-task recommendation for a stronger model/effort. A warning cannot guarantee execution is paused before the model consumes tokens. Document `preflight` for users who want to decide **before** execution.
2. For **delegated agents**, the root supplies generic task text without selecting worker model/effort; the router owns these choices. Preserve any existing model/effort pin and named custom profile. A runtime-verified generic default type is not itself a pin. Classify only eligible unpinned spawns once; modify only schema-valid routing fields, leaving task and other arguments unchanged.
3. **Fail open** on classifier failure, invalid catalog, unknown schema, timeout, lack of permission, hook conflict or unavailable credentials: the native tool invocation runs with its original inputs. Make fallback visible in logs. For other unexpected hook failures, never turn an authorization decision into broader permission.
4. **Effort choice is conditional on runtime support.** Codex can carry model + effort on eligible `spawn_agent` in documented community implementations, but must be verified locally. Claude `Agent` effort support must be proven; otherwise route model while leaving effort inherited or use an officially supported agent/profile mechanism.
5. **TypeSafe privacy:** no prompt sent without configuration and clear disclosure; default deployment should require Jev opt-in/key, with conservative native fallback. Keep exact prompt out of local logs. Test prompt minimization and redaction without breaking classification.

**Confirmed scope (2026-10-19):** CLI and local desktop code sessions are mandatory for both runtimes; separate surface smoke evidence is required even with a shared harness. Account availability of configured target models is assumed by user instruction, not a prerequisite entitlement-discovery task. Runtime ID/version mapping, supported fields/efforts and effective execution remain validation gates.

## Delivery phases and exit gates

| Phase | Scope | Exit gate | Deliverable |
|---|---|---|---|
| P0. Discovery | Pin versions, inspect fork, official hooks, Jev SDK, model catalogs | Demonstrated minimal interception on **both** runtimes; no unverified assumptions | Capability matrix + evidence transcripts |
| P1. Contracts | Shared event models, config, catalog, decision records | Schema/contract tests and fixture validation pass | Stable core interfaces, schema v1 |
| P2. Classifier + policy | Jev adapter, deterministic safety gates, effort optimizer, fallbacks | Golden policy cases pass; Jev failures no-op | Shared executable routing engine |
| P3. Boundaries + warnings | Stateful cheap gate; dedupe; advisory warning | No Jev calls for tool-loop/obvious continuation; once-per-task warning | Root advisory hooks for both |
| P4. Claude | Hook mutation for Agent/Task, model validation, feedback | Claude live smoke proves actual subagent model and unchanged root | Claude plugin adapter |
| P5. Codex | Native hook/plugin for eligible spawn_agent, effort validation, trust flow | Codex live smoke proves actual subagent model/effort and unchanged root | Codex plugin adapter |
| P6. Evals | Offline labeled task suite + shadow/on rollout | Meets qualitative gates, guards pass, regressions checked | Evaluation results + tuning decisions |
| P7. Release | Packaging, docs, toggles and rollback | Fresh-machine install/uninstall tested; rollback works | Versioned distributable components |

**Blocking rule:** If any required primitive (e.g., mutable subagent model) does not work on the installed runtime, stop that adapter's auto-routing rollout; offer a supported tool/profile-mediated route and publish a real capability gap. **Do not silently fake successful routing.** Continue parallel work on the other adapter and shared core; do not declare V1 fully delivered until both adapters have an actual usable integration (even if they legitimately have different supported behaviors).

## Recommended ordering / parallel tracks

- **Critical path:** `Audit -> SDK contract -> shared policy -> boundary detector -> adapters -> live smoke -> eval/rollout`.
- Claude and Codex adapters can run in parallel after shared contracts settle, but keep independent recorded proof of accepted `updatedInput` semantics.
- Policy/AA research and privacy/security work can run beside adapters; **do not block essential correctness on recrawling external benchmark scores**.
- Start in `shadow` or `advise`, record recommendations versus actual host execution, then enable subagent auto-routing by one runtime at a time.

## Milestones

- **M0 / Feasibility:** one verified interception/argument replacement smoke per harness; exit early on incompatibility.
- **M1 / Shared core:** Jev selection + hard policy and model registry fully testable without a live CLI.
- **M2 / Claude pilot:** root warn-only and unpinned subagent automatic routing (or formally documented support limitation).
- **M3 / Codex pilot:** root warn-only and native spawn model + effort selection verified.
- **M4 / Operational readiness:** telemetry, security checks, version matrix, CI, feature flags, rollback.

## User journeys

**Main session upgrade advisory:** Sonnet is currently selected; user begins a fresh architecture task; boundary gate identifies a new task; Jev predicts high complexity; policy determines that Opus or a higher effort might materially help; `UserPromptSubmit` writes a **nonblocking advisory** with reason. The session remains Sonnet. If user wants to switch before executing, they must invoke an explicit preflight workflow before sending the execution request; a normal hook warning alone is not a pre-execution approval gate.

**Subagent delegation:** Root remains any selected model. Root invokes `Agent`/`Task` (Claude) or `spawn_agent` (Codex) with an unpinned task; `PreToolUse` hooks inspect only the spawn; Jev gets a bounded task description; policy chooses a supported model + effort (or model only where appropriate); hook returns validated `updatedInput`; host executes; logs compare requested vs resolved model where the runtime exposes it; result returns to unchanged root.

**Continuation:** User says “now add two tests” after implementation. Cheap boundary gate considers it continuation and reuses task identity. No Jev root call; a *new* subagent spawn may still be routed as a distinct delegated task.

## Explicit review checkpoints

- **Architecture review after P0:** choose all-per-hook vs hybrid vs explicit tool only, based on demonstrated native capabilities.
- **Security/privacy review before live Jev:** confirm what task text leaves the machine, credential storage, and permissions.
- **Deployment review after P5:** check whether active model/effort was actually used, not merely requested.
- **Policy review after P6:** adjust AA priors using locally collected completion quality and retries.

# 07 — Architectural Decisions, Risks & Research Sources

## ADR-001 — One core, two native adapters

**Decision:** shared task-boundary, classifier, policy, model registry, logging and config; separate Claude/Codex wrappers for event schemas and mutations. **Why:** avoids divergent heuristics and duplicate vendor selection logic. **Alternative rejected:** two independent forks with policy duplication.

## ADR-002 — No inference proxy by default

**Decision:** use official CLI and native hooks. `jev-claude`/`jev-codex` wrappers are references only, not dependencies. **Why:** preserves CLI rollout, auth, permissions, and existing subscriptions as much as the native hook interface permits. **Tradeoff:** cannot necessarily alter every low-level inference request or enforce choices outside hook coverage.

## ADR-003 — Parent advisory-only

**Decision:** root model and effort are exactly those currently selected by the user/runtime. For new work, emit nonblocking quality recommendation; never change session or settings. **Tradeoff:** a normal prompt may begin running before user manually changes model. Offer explicit `preflight` for true before-execution decision. A `UserPromptSubmit` warning is NOT equivalent to an approval gate.

## ADR-004 — Structural task boundaries with conservative abstention

**Decision:** always recognize native child spawns; recognize root task boundaries through strong events/state; do not run Jev on each prompt. Ambiguous root continuity => abstain or explicit preflight. **Tradeoff:** will miss some new root tasks; intentional preference to avoid surprise cost/latency and warning spam.

## ADR-005 — User pins always win

**Decision (confirmed 2026-10-19):** generic root delegations omit model/effort so the router chooses them. Existing model/effort pins and custom/unknown profiles bypass routing before classification; a verified generic default type alone does not. Hooks do not infer human-versus-root provenance. **Tradeoff:** no effort-only routing when model pinned in V1. Update product guidance, not global user instructions without separate scope/approval.

## ADR-006 — Jev classification separate from AA model policy

**Decision:** Jev measures task needs; policy chooses actual available model + effort with capability floor. **Why:** index/cost tradeoffs change, versions and availability differ, effort is not uniform. **Alternative rejected:** use Jev's existing cheapest-tier mapping verbatim for root and children.

## ADR-007 — Fail-open + real-execution evidence

**Decision:** no-op tool input if uncertain; never claim a chosen model actually ran without host evidence. **Tradeoff:** some tasks inherit potentially suboptimal native model; better than brittle routing that breaks tools or permissions.

## ADR-008 — No raw prompt logging; explicit TypeSafe opt-in

**Decision:** local task excerpt minimized, authenticated external classification opt-in, redacted/hardened state; documentation transparent about data leaving the machine. **Tradeoff:** reduced context may impair classification; measure.

## ADR-009 — Conditional Claude worker effort

**Decision:** do not assume Claude Agent accepts per-child effort. Verify current runtime; dynamic effort only if supported by official schema/agent definitions. Codex `spawn_agent` is a stronger candidate for direct model+effort mutation. **Tradeoff:** feature parity may differ but no fake feature claims.

## ADR-010 — Keep plugin open to a tool-based mode

**Decision:** an on-demand read-only `router preflight` command is included. MCP is optional if an official native hook is sufficient. **Why:** explicit tool invocation adds tokens and relies on model compliance; it is less appropriate for every prompt but useful for planning and early user confirmation.

## Primary-source reference ledger (checked 2026-10-17)

| ID | Source | Supports / caution |
|---|---|---|
| S01 | https://code.claude.com/docs/en/hooks | Official lifecycle; `UserPromptSubmit`, `PreToolUse` with `updatedInput`, `SubagentStart`, `TaskCreated`, `PreModelSwitch`, `PostModelSwitch`. Event presence ≠ task semantics or tested worker model mutation. |
| S02 | https://learn.chatgpt.com/docs/hooks | Official Codex hook events, local function tool coverage, `spawn_agent` matcher `Agent`, active `model`, `updatedInput` with `permissionDecision:"allow"`, trust and limitations. |
| S03 | https://developers.openai.com/plugins/build/plugins | Official Codex plugin packaging, hook discovery, `PLUGIN_ROOT` and `PLUGIN_DATA`, explicit trust review. |
| S04 | https://github.com/tzachbon/claude-model-router-hook | Public upstream fork base; heuristics-first, optional Claude fallback, Agent/Task hook, default warn mode. |
| S05 | https://github.com/tzachbon/claude-model-router-hook/blob/main/CHANGELOG.md | Python router rewrite, effort-first policy, hook routing behavior. Pin audited commit locally. |
| S06 | https://github.com/gargpratyush/jev-router/blob/master/src/router.mjs | Sample TypeSafe SDK usage `TypeSafeClient.systemOne`; client timeout/retry, normalization references. A proxy implementation is not mandatory to use Jev. |
| S07 | https://github.com/gargpratyush/jev-router/blob/master/src/policy.mjs | Jev's tier/low-confidence/context switching policy; reference, not our architecture. |
| S08 | https://github.com/gargpratyush/jev-router/blob/master/src/config.mjs | Sample task complexity, reasoning and tool questions, model descriptions; model examples can age. |
| S09 | https://github.com/guilhem/codex-subagent-router | Community Jev + Codex `spawn_agent` hook using task profiles, model/effort selection. Verify actual runtime and code; activity/popularity low. |
| S10 | https://github.com/hooyao/codex-model-router | Community Codex router/plugin reference; not an official guaranteed capability. |
| S11 | https://developers.openai.com/api/docs/guides/reasoning | Model-specific effort support; API reasoning support does not automatically imply Codex native child tool supports that parameter. |
| S12 | https://artificialanalysis.ai | Benchmark source to recheck methodology and dates. Local historical AA notes are summarized separately in `04_ROUTING_POLICY_AA.md`, and are **not fresh verified data**. |

## Source confidence classification

- **Verified by published official documentation:** events, general rewriting mechanism and official plugin trust semantics (S01–S03).
- **Verified from public repository READMEs/source (but not locally executed):** upstream heuristics, Jev SDK usage, example Codex integrations (S04–S10).
- **Not yet verified:** installed runtime CLI versions, correct model catalogs and availability, Claude per-agent effort, real host execution route, stability of hooks across surfaces, TypeSafe retention policy and actual cost savings.

## Priority risks and mitigations

| Risk | Severity | Mitigation / gate |
|---|---|---|
| Host ignores worker model/effort rewrite | Critical | Early live smoke before core rollout; explicit `actual_unverified`; disable unsupported auto route |
| `permissionDecision:allow` changes approval semantics | Critical | Scope to known agent spawn only; test sandbox/approval path, no generic tool rewrite |
| Parent warning arrives after work begins | High | Honest UX; explicit manual preflight; no claim of guaranteed pause |
| Jev transmits proprietary task text externally | High | Opt-in, payload minimization, secret checks, vendor retention review |
| Hook path misses hosted tools or desktop surfaces | High | Per-version/surface capability matrix; no blanket coverage claims |
| Undefined merge order when two hooks rewrite spawn | High | Coexistence tests, conflict detection, opt-out/disable route if ambiguity |
| Historical AA priors wrong/mixed version | High | Dated snapshots, methodological check and local eval before tuning |
| Jev SDK only in JavaScript while upstream Python | Medium | Stable interface bridge or documented HTTP SDK; benchmark process overhead |
| User subscription quotas unlike API dollars | Medium | Use quota pressure/latency/task success proxies; never assert direct price savings |
| Task boundary false positive/negative | Medium | Structural events, conservative abstain, explicit preflight, sequence tests |
| Model alias points to unexpected revision | Medium | Versioned available-model registry and exact supported IDs |
| Root model changes manually during long session | Medium | Event/state refresh; never revert selection; no in-flight rewrite |
| Parser / config injection via untrusted prompt | High | Strict JSON parse, no shell interpolation, treat task as data not instructions |
| Logs disclose prompts/secret or persist too long | High | Hashes only by default, file perms, bounded retention, explicit debug warnings |

## Open questions for the implementation audit

1. Which Claude Agent/Task fields are available in the **exact** installed CLI? Can effort be specified natively per subagent?
2. Does the Codex installed `spawn_agent` tool expose independent model and reasoning_effort for every surface, and how can the effective worker route be verified?
3. Does the official native hook warning appear before model invocation in that surface, or only as developer context? What does the user actually see?
4. Can the TypeSafe SDK be invoked from Python through an official transport, or is a slim Node bridge preferred? What are privacy/retention and failure semantics?
5. What can be obtained from a reliable model catalog, and how is the catalog scoped to actual signed-in account and local installation?
6. What counts as task completion vs continuation for non-delegating root tasks, and is explicit preflight the best opt-in?
7. What default confidence and material-gain threshold minimize unnecessary root warnings?
8. Should user-provided explicit worker model with unspecified effort remain completely pinned (v1 yes) or permit effort-only routing later?

## Attribution / reuse

The two referenced major repos were inspected as public source/reference projects, not copied wholesale into this artifact. Before implementing a fork or copying code, verify the repository's current LICENSE and attribution requirements. Avoid reusing a source-available noncommercial repository in commercial code without licensing review.

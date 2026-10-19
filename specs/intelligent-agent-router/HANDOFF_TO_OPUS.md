# Handoff Prompt — Implement Intelligent Agent Router (Claude Code + Codex)

Act as a **Principal AI Infrastructure Engineer** implementing a fork of `tzachbon/claude-model-router-hook` into a **unified intelligent task-aware model and reasoning-effort router for Claude Code and Codex**.

## Read first — binding specification

This handoff package contains the source of truth:

1. `README.md`
2. `docs/00_REVISED_PLAN.md`
3. `docs/01_PRODUCT_SPEC.md`
4. `docs/02_TECHNICAL_DESIGN.md`
5. `docs/03_RUNTIME_ADAPTERS.md`
6. `docs/04_ROUTING_POLICY_AA.md`
7. `docs/05_TASK_BACKLOG.md` and `tracking/tasks.csv`
8. `docs/06_TEST_EVAL_PLAN.md`
9. `docs/07_ADRS_RISKS_SOURCES.md`

Please read these files and the current local repository before modifying code.

## What we are building

- **Root/orchestrator** = whichever model and reasoning effort is *already active in the user's session*. Never change either automatically, even if the root is Sonnet/Terra instead of Opus/Sol. On a confidently detected **new task**, a stronger route may trigger a **nonblocking capability advisory** only; one warning per task. If the user wants to decide *before* sending the task, provide a separate explicit preflight command. Do not promise a normal hook will pause inference.
- **Workers/subagents** = when a native child spawn is **unpinned**, classify it using TypeSafe Jev; apply a benchmark-informed policy to choose a **supported available model and independent effort**. Explicit model/effort/agent-type selections must override automatic routing. Do not alter child prompts, permissions or unrelated tools. If dynamic Claude worker effort is unsupported, honestly implement model routing only for that field and report the capability gap.
- **Task boundary** = *not every user turn*. Structural `PreToolUse` agent-spawn events trigger child assessments. Root `UserPromptSubmit` uses a cheap, stateful gate; continuations or uncertainty usually skip Jev. Never run an expensive classifier merely to decide on every message whether a classifier is needed.
- **Integrations** = official `claude` and `codex` CLIs, one shared routing/policy core and two runtime-specific adapters **in V1**. No modified binaries and no inference proxy as default.
- **Research basis** = maintain task-class, model and effort routing heuristics informed by previous Artificial Analysis comparisons. Read `04_ROUTING_POLICY_AA.md` and explicitly separate historical research notes from current verified benchmark reports.

## Confirmed scope refinements (2026-10-19)

CLI and local desktop code sessions are required for both runtimes, with independent surface smoke evidence. Generic root delegations omit worker model/effort so the router chooses; explicit pins/custom profiles remain protected and global AGENTS instructions are not silently edited. Assume target account availability per user instruction while validating exact runtime IDs/version, supported fields/efforts and actual execution. Target versions: Fable 5.1, Luna 6, Terra 6, Sol 6.1, Astra 6. These refinements do not authorize implementation beyond the current user's request.

## How to work

1. **Audit before edit:** inspect all code, tests, license and hooks in local fork; identify version and compare against official Claude hooks, Codex hooks/plugin docs, Jev SDK source and existing community integration repos.
2. **Run minimum feasibility spikes** `RTE-003`, `RTE-004`, `RTE-005` first; record live observations of tool argument rewriting **and actual executed child model/effort** for both runtimes. Treat unsupported features as constraints, not silently solved problems.
3. **Produce capability matrix** with `supported/unsupported/unverified` status and evidence, especially Claude per-agent effort and Codex plugin trust/hosted tool limitations. Then finalize an ADR for implementation mechanism.
4. **Implement shared core + adapters** incrementally using the phased backlog, with unit + contract tests. Respect public behavior and installed auth; maintain safe disabled/shadow modes.
5. **Run real smoke tests**, verify model/effort per worker rather than merely mock `updatedInput`, and no root model/effort mutation.
6. **Evaluate** task boundary precision, Jev latency/call rate, quality/retries and logging privacy. Prefer a conservative no-op on uncertain classification.
7. **Document** full install/uninstall instructions for both CLIs, configuration, diagnostics, trust and limitations. Keep `tasks.csv` / backlog statuses updated as work progresses.

## Required early output

Before substantial implementation, provide a concise but rigorous report with:

- existing fork architecture and baseline test state;
- exact local Claude/Codex versions and discovered model/effort capabilities;
- verified pre-tool rewrite mechanics for both;
- task-boundary strategy with false-positive tradeoffs;
- Jev SDK invocation/transport plan and privacy impact;
- confirmed blocker list, mitigation and next 1–2 PRs.

Proceed autonomously if the audited architecture supports requirements. If a non-negotiable assumption fails, present the blocker and supported alternative before introducing a fundamentally different mechanism.

## Definition of done

Both official runtimes have a **usable and demonstrated** integration (not merely a stub); root model/effort remain the user's choice; workers route only on eligible unpinned spawns; no unnecessary Jev reclassification; invalid routes fail safely; decision logs are private; tests and versioned documentation exist. A partially supported feature must be labeled accurately and excluded from claims.

**Start now with the audit and the first three feasibility spikes.**

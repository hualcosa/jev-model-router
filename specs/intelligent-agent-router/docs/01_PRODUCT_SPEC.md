# 01 — Product Requirements Specification (PRS)

## 1. Product thesis

Implement an intelligent **task-aware model and effort router** across the official Claude Code and Codex environments, without routing each message or replacing CLI/inference stacks. It should recommend a main-session upgrade only at a detected new task boundary, and automatically choose an appropriate **subagent** model (+ effort when supported) when an agent delegates new work. Think of it as an **advisory layer for the root** and **execution-routing layer for workers**.

## 2. Actors and surfaces

- **User:** chooses the root model/effort, defines budgets and overrides, can inspect recommendation and switch manually.
- **Root/orchestrator:** executes plans in the active Claude Code or Codex session; delegates work through native agent tools.
- **Routing core:** pure classifier/policy/boundary decisions; never performs the task itself.
- **Runtime adapter:** observes lifecycle events, validates and optionally rewrites native tool inputs.
- **Jev / TypeSafe:** external classifier of task requirements; receives a bounded request only if allowed.
- **Subagent:** executes with supported model/effort, subject to normal host permissions.

## 3. Functional requirements

### Root / advisory

- **FR-001** Detect actual root model from trusted runtime metadata. Never infer root solely from the name in an instruction file. Refresh on resume/model change when possible.
- **FR-002** Root model and effort must not be programmatically mutated by the router. Model switch events may update **observed state** only.
- **FR-003** Trigger root assessment only at an identified new logical task, not every prompt. Suppress clear continuations and user acknowledgments. Under ambiguous boundary conditions, prefer no costly assessment and expose manual `preflight`.
- **FR-004** Display **one nonblocking warning per task + recommendation fingerprint** only when materially better than current route; include chosen target, delta rationale, classifier confidence/uncertainty, and manual `/model` or config guidance. Do not claim the warning pauses execution.
- **FR-005** Suppress warnings about a model outside the signed-in account catalog, or about unsupported effort. Explicitly distinguish “use higher effort on same model” versus “change model.”
- **FR-006** When root model changes manually, refresh the registry/state and allow a new advisory recommendation as appropriate without migrating in-flight tasks.

### Subagents / automatic routing

- **FR-007** Match only eligible, native agent-creation tools (`Agent`/`Task` for Claude; `spawn_agent`/matched native local function tools for Codex, as verified in installed version).
- **FR-008** The root delegates generic tasks without preselecting model/effort; the router owns those choices. Preserve explicit human/policy pins and custom profiles. Any non-null model/effort already present bypasses **all** modifications before classification: do not infer its human/agent origin or erase it. A runtime-verified generic default agent type alone is eligible; custom/unknown types bypass. Log `skipped_explicit_override`. Do not silently edit global delegation instructions.
- **FR-009** For an eligible unpinned spawn, request at most one Jev classification. Do not request another classification for internal worker tool calls or `PostToolUse`.
- **FR-010** Produce a valid route from **actual available models + supported efforts**; never guess IDs, insert unsupported fields or force a model unavailable to the account.
- **FR-011** `updatedInput` must contain original arguments plus only permitted route overrides; do not change task text, input items, sandbox, approvals, worktree, or tool permissions.
- **FR-012** Classification timeout, invalid result, unsupported schema, provider failure, untrusted hook, conflict, or missing key defaults to original native arguments (fail-open). Security decisions from other hooks remain intact.
- **FR-013** Model selection remains stable for the worker's execution; do not induce in-worker per-turn model switching.
- **FR-014** Track requested versus actual agent model and effort when the host emits them, otherwise mark `actual_unverified` — never claim success solely from rewrite emission.
- **FR-015** Concurrency-safe state: two parallel agent spawns must not overwrite each other's decision or share a mutable “last model” singleton.

### Policy / configuration / observability

- **FR-016** Split task requirements, model choice and effort choice into independently testable components.
- **FR-017** Supply versioned policy per vendor/run mode; defaults are priors from our Artificial Analysis studies, not hard model IDs. Support configurable ceilings/floors for frontier models, usage and risk.
- **FR-018** Load API key from environment or secret provider; never write it into project config, logs, traces, error messages, or public artifacts.
- **FR-019** Provide local `disabled`, `shadow`, `warn` and `auto_workers` behavior. `shadow` must not modify tools; `auto_workers` never modifies parent.
- **FR-020** Store minimal telemetry: IDs, hashes, timings, recommended tier, final route, confidence, fallbacks; do not log raw prompts by default.
- **FR-021** Supply an auditable why/explain capability via a CLI command/skill (optional read-only MCP facade) that reads **recorded** decisions; do not make a fresh Jev call for explanations.
- **FR-022** Fresh installs for BOTH runtimes must be documented, independent, reversible and tested in both CLI and local desktop code sessions. Desktop is mandatory, not optional; shared harness does not replace per-surface smoke. No modified official binary or inference proxy required.

- **FR-023** Router-selected candidates must honor the explicit target versions in `04_ROUTING_POLICY_AA.md` §1.1: Fable 5.1, Luna 6, Terra 6, Sol 6.1 and Astra 6. Verify the runtime ID-to-version mapping and account availability; do not silently substitute another generation. Unverified/unavailable candidates are excluded with a reason code; if no eligible route remains, preserve native inputs. This does not constrain the user's existing root selection or explicit worker pins.

## 4. Nonfunctional requirements

- **NFR-001 Reliability:** no-op / fail-open on Jev/adapter error; warnings never block ordinary task flow.
- **NFR-002 Latency:** classification has explicit request budget (prototype default <=2.5 s wall); verify p50/p95 before rollout. Cheap gate avoids Jev on clear continuation.
- **NFR-003 Privacy:** explicit documented third-party text transmission; data minimization and secrets redaction where practical; no raw prompt logs; 0600 files, 0700 state directories on POSIX.
- **NFR-004 Performance:** one new subagent class => <=1 Jev request (excluding bounded transport retries); no reclassification within a tool loop; avoid spawning an additional Claude or Codex model just to run the gate.
- **NFR-005 Maintainability:** an independent core; no runtime-specific constructs leak into policy logic.
- **NFR-006 Compatibility:** test supported released versions and an installed current version; detect unknown fields; avoid assumptions about private JSON/transcripts.
- **NFR-007 Security:** tool argument rewrite must not broaden permissions. A hook `allow` required to apply `updatedInput` may affect the tool's permission path — test host semantics and do not use on sensitive tools; restrict to known agent spawns only.
- **NFR-008 Catalog truth:** target model account availability is assumed per explicit user instruction, with provenance `user_assumption`, not mislabeled as verified. Do not block on entitlement discovery. Exact ID/version mapping and supported efforts/tool fields must still be validated; unknown technical support causes abstention. Runtime rejection is recorded and handled safely, with no silent generation substitution.

## 5. User stories and BDD acceptance scenarios

### US-01 Advisory for inadequate root

**Given** a Claude Code session with Sonnet active, **when** the user starts a fresh difficult architecture task, **and** the classifier/policy strongly recommend Opus, **then** present an advisory without switching Sonnet or altering effort. A subsequent “go ahead” continuation for the same task does not call Jev again or reissue the warning. The user may manually switch via supported UX.

### US-02 Effort-only advisory

**Given** a Codex session with a strong model on Medium, **when** a fresh task needs heavier deliberation but another model is not clearly better, **then** recommend High on the same model, provided it is available. Do not automatically change session effort.

### US-03 Auto route a simple worker

**Given** an unpinned native subagent spawn to inspect file structure, **when** Jev returns high-confidence simple requirements and a fast model is available, **then** rewrite the child’s model (and supported effort); parent stays unchanged; original task payload is byte-for-byte equivalent except router-controlled fields.

### US-04 Keep explicit pins

**Given** a spawn with explicit model OR effort OR custom/unknown profile, **when** the hook intercepts it, **then** no Jev call and no argument mutation. A verified generic default type without model/effort is eligible, so the router can choose them. Existing pins win regardless of whether the root or user supplied them.

### US-05 Do not route internal steps

**Given** a worker doing multiple tool calls, **when** `PostToolUse`, follow-up tool calls, or internal continuations occur, **then** no further Jev calls for that worker.

### US-06 Fail-open

**Given** a bad Jev key, unsupported effort, or timeout, **when** a new unpinned spawn arrives, **then** native spawn runs with original args, event records `deferred` and no secrets.

### US-07 Concurrent workers

**Given** three parallel worker spawns, **when** hooks run concurrently, **then** each maps correctly to its own task/tool ID, no shared state overwrite, and idempotent duplicate hooks do not make duplicate outbound Jev calls.

### US-08 Warning timing

**Given** user submits a task normally, **when** router prints a warning on `UserPromptSubmit`, **then** describe it as a recommendation **during** submission, not a stop-and-confirm interaction. For guaranteed pre-execution control provide an **explicit user-invoked `router preflight "..."`** that assesses before user sends the task to the root.

## 6. Rules of precedence

1. Host runtime security, supported schema, and active catalog.
2. Explicit human/policy pins or custom agent profile.
3. Native model/effort constraints and non-negotiable critical-task floors.
4. Jev confidence and classification.
5. Benchmark-informed prior and tie-breakers (quality-adjusted latency / successful-task efficiency).
6. Fallback to native inheritance when unclear.

## 7. Definition of done

- Two real adapters installed and exercised against actual official CLIs (not mocked-only).
- Root model/effort unchanged in every scenario; warnings correct and deduped.
- Auto worker selection verified **at actual execution** for supported fields, not merely `updatedInput` emission.
- No Jev on obvious continuations; once per eligible worker spawn.
- Unknown/unavailable model and effort fail open.
- Privacy, credential and hook trust constraints verified.
- Fully versioned policy/registry, disabled mode, uninstall/rollback, install docs, CI and evaluation report.

# 05 — Executable Task Backlog

**48 work items**, IDs `RTE-001`–`RTE-048`. Importable CSV in `../tracking/tasks.csv`.

## Planning conventions

- `P0` = must-have for functional/secure V1; `P1` = release quality/observability or supporting capability (some P1 items may become release-blocking depending on audit).
- Size = qualitative engineering effort: `S` ~0.5–1 day, `M` ~1–3 days, `L` ~3–6 days; not a delivery promise.
- Every item requires a code/test/docs diff or an evidence artifact. `Done` means acceptance is **demonstrated**, not merely explained.
- `RTE-003`, `RTE-004` and `RTE-005` are early risk-reduction spikes. If a runtime-specific primitive fails, stop and revisit architecture.

## Quick index

| Phase | Area | P0/P1 tasks |
|---|---|---|
| P0 | Capability audit | 6 / 0 |
| P1 | Core contracts | 4 / 1 |
| P2 | Jev + policy | 5 / 2 |
| P3 | Task boundaries + warning | 4 / 2 |
| P4 | Claude adapter | 3 / 4 |
| P5 | Codex adapter | 4 / 1 |
| P6 | Tests and evaluation | 3 / 4 |
| P7 | Release | 3 / 2 |

---

## P0 — Capability audit

### RTE-001 — Inventory fork and pin baseline

**Status:** done · Evidence: `../evidence/p0/`

**Priority:** P0 · **Size:** S · **Depends on:** none

**Implementation:** Map existing Python router, configs, hooks, tests and installer; record commit SHA and license.

**Acceptance / evidence:** A repository map with file paths, version, baseline test results, and list of features to retain exists.

### RTE-002 — Record local runtime versions and environment

**Status:** done · Evidence: `../evidence/p0/`

**Priority:** P0 · **Size:** S · **Depends on:** none

**Implementation:** Capture claude/codex versions and plugin/hook status without secrets; note CLI vs desktop surfaces.

**Acceptance / evidence:** Compatibility matrix includes installed versions, mode, hook trust, active model source and baseline behavior.

### RTE-003 — Claude Agent mutation capability spike

**Status:** done · Evidence: `../evidence/p0/`

**Priority:** P0 · **Size:** M · **Depends on:** RTE-001,RTE-002

**Implementation:** Use a minimal PreToolUse fixture for Agent/Task and verify updatedInput actual child execution.

**Acceptance / evidence:** Live smoke transcript confirms whether requested model is applied and how permissions behave.

### RTE-004 — Codex spawn_agent mutation and effort spike

**Status:** done · Evidence: `../evidence/p0/`

**Priority:** P0 · **Size:** M · **Depends on:** RTE-002

**Implementation:** Use official Codex hooks to mutate one unpinned spawn_agent with valid model and reasoning_effort.

**Acceptance / evidence:** Live smoke verifies actual spawned child model and effort, or marks precise capability unsupported.

### RTE-005 — Audit TypeSafe SDK and API contract

**Status:** done · Evidence: `../evidence/p0/`

**Priority:** P0 · **Size:** M · **Depends on:** none

**Implementation:** Inspect TypeSafe SDK methods, response schemas, auth/privacy policies, latency and transport options.

**Acceptance / evidence:** Small standalone Jev call produces validated result or a reproducible block; no proxy needed.

### RTE-006 — Capability and feasibility decision record

**Status:** done · Evidence: `09_FEASIBILITY_ADR.md`

**Priority:** P0 · **Size:** S · **Depends on:** RTE-003,RTE-004,RTE-005

**Implementation:** Consolidate verified/supported/unknown capabilities and choose smallest viable architecture.

**Acceptance / evidence:** Reviewer signs off an ADR or identifies blocker/alternative before production implementation.


## P1 — Core contracts

### RTE-007 — Define typed cross-runtime event contracts

**Status:** done · Evidence: `../evidence/p1/core-contracts.json`; integrated into primary local main (uncommitted).

**Priority:** P0 · **Size:** M · **Depends on:** RTE-006

**Implementation:** Create TaskEnvelope, TaskRequirements, RoutingDecision, ProviderResult with schema versions.

**Acceptance / evidence:** Serialization roundtrip and invalid-input fixture tests pass.

### RTE-008 — Define and validate config schema v1

**Status:** done · Evidence: `../evidence/p1/core-services.json`; reviewed and integrated into primary local main (uncommitted).

**Priority:** P0 · **Size:** M · **Depends on:** RTE-007

**Implementation:** Create global/project config resolution, defaults, validation, modes and opt-ins.

**Acceptance / evidence:** Misconfigured fields error clearly; active parent auto-switch is impossible through schema.

### RTE-009 — Implement per-runtime model/effort inventory abstraction

**Status:** done · Evidence: `../evidence/p1/core-services.json`; reviewed and integrated into primary local main (uncommitted).

**Priority:** P0 · **Size:** M · **Depends on:** RTE-007

**Implementation:** Resolve exact target model IDs/versions and supported effort fields. Account availability is assumed by user instruction; record provenance separately from verified technical support.

**Acceptance / evidence:** No unavailable model or unsupported effort can be routed in unit tests. Registry distinguishes desired version from runtime ID and verifies exact mappings for Fable 5.1, Luna 6, Terra 6, Sol 6.1 and Astra 6 (FR-023; TC-041…043); unknown/different generations cannot silently substitute.

### RTE-010 — Define sanitized task description builder

**Status:** done · Evidence: `../evidence/p1/core-services.json`; reviewed and integrated into primary local main (uncommitted).

**Priority:** P1 · **Size:** M · **Depends on:** RTE-007,RTE-005

**Implementation:** Trim irrelevant context, redact obvious secrets and preserve task semantics; configurable privacy opt-in.

**Acceptance / evidence:** Fixtures show no API keys or credentials in generated Jev inputs; bounded payload size.

### RTE-011 — Establish deterministic policy fixtures

**Status:** done · Evidence: `../evidence/p1/policy-boundaries.json`; reviewed and integrated into primary local main (uncommitted). Cross-process coordination remains RTE-020.

**Priority:** P0 · **Size:** S · **Depends on:** RTE-007,RTE-009

**Implementation:** Write golden input/output cases before implementing policy.

**Acceptance / evidence:** Include mechanical, implementation, architecture, risk, pins, catalog conflicts and abstain.


## P2 — Jev + policy

### RTE-012 — Implement Jev client adapter

**Status:** done · Evidence: `../evidence/p1/core-services.json`; reviewed and integrated into primary local main (uncommitted).

**Priority:** P0 · **Size:** M · **Depends on:** RTE-005,RTE-007,RTE-010

**Implementation:** Create independent SDK/transport wrapper with wall deadline and injectable fake.

**Acceptance / evidence:** Successful Jev response normalizes and timeout/failure returns defer without CLI disruption.

### RTE-013 — Implement strict Jev response normalizer

**Status:** done · Evidence: `../evidence/p1/core-services.json`; reviewed and integrated into primary local main (uncommitted).

**Priority:** P0 · **Size:** M · **Depends on:** RTE-012

**Implementation:** Parse actual SDK schemas and reject absent/conflicting out-of-range confidence and choices.

**Acceptance / evidence:** Malformed provider outputs fail open with reason code and no invented confidence.

### RTE-014 — Implement model capability floor and ranking

**Status:** done · Evidence: `../evidence/p1/policy-boundaries.json`; reviewed and integrated into primary local main (uncommitted). Cross-process coordination remains RTE-020.

**Priority:** P0 · **Size:** L · **Depends on:** RTE-009,RTE-011

**Implementation:** Separate requirements from models; enforce risk/version constraints and policy availability.

**Acceptance / evidence:** Golden task cases choose only eligible verified candidates; hard capability floor always wins.

### RTE-015 — Implement effort selection policy

**Status:** done · Evidence: `../evidence/p1/policy-boundaries.json`; reviewed and integrated into primary local main (uncommitted). Cross-process coordination remains RTE-020.

**Priority:** P0 · **Size:** M · **Depends on:** RTE-009,RTE-011,RTE-014

**Implementation:** Choose valid effort after model and runtime capabilities; provide advisory-only when unsupported.

**Acceptance / evidence:** Same model may have different effort per task; no invalid effort field emitted.

### RTE-016 — Implement override, abstain and failure precedence

**Status:** done · Evidence: `../evidence/p1/policy-boundaries.json`; reviewed and integrated into primary local main (uncommitted). Cross-process coordination remains RTE-020.

**Priority:** P0 · **Size:** M · **Depends on:** RTE-013,RTE-014,RTE-015

**Implementation:** Handle explicit pins, custom agents, low confidence, critical floor, Jev missing and fallback.

**Acceptance / evidence:** Existing model/effort pins and custom/unknown profiles cause zero Jev calls and zero mutations; verified generic types with no pins remain eligible; failures preserve native inheritance.

### RTE-017 — Version policy and registry snapshots

**Status:** done · Evidence: `16_VERSIONED_SNAPSHOTS_AND_INVENTORY.md`, `../evidence/p1/versioned-snapshots.json`; immutable content-addressed snapshots persisted before native/provider assessment, historical records decode exactly, stale routes abstain. Primary local main, uncommitted.

**Priority:** P1 · **Size:** S · **Depends on:** RTE-014,RTE-015

**Implementation:** Persist policy/version and discovered catalog metadata without credentials.

**Acceptance / evidence:** Each decision records versions; changing policy does not corrupt older event decoding.

### RTE-046 — Add Jev request privacy preview and consent flow

**Status:** done · Evidence: `14_PREFLIGHT_AND_PRIVACY_PREVIEW.md`; local payload preview never sends; --send cannot grant global consent, nonfixture text rejected under synthetic-only consent. Integrated into primary local main (uncommitted).

**Priority:** P1 · **Size:** M · **Depends on:** RTE-010,RTE-012

**Implementation:** Implement debug preview of payload leaving machine; require explicit opt-in for provider.

**Acceptance / evidence:** User can inspect outbound fields without printing secrets; no provider call before opt-in.


## P3 — Task boundaries + warning

### RTE-018 — Implement root task-boundary state machine

**Status:** done · Evidence: `../evidence/p1/policy-boundaries.json`; reviewed and integrated into primary local main (uncommitted). Cross-process coordination remains RTE-020.

**Priority:** P0 · **Size:** L · **Depends on:** RTE-007,RTE-008

**Implementation:** Implement new_task/continuation/unknown with per-session task state and stable hints.

**Acceptance / evidence:** Sequence tests show continuations and tool loops never call Jev; unknown abstains.

### RTE-019 — Implement structural child-spawn detection

**Status:** done · Evidence: `../evidence/p1/policy-boundaries.json`; reviewed and integrated into primary local main (uncommitted). Cross-process coordination remains RTE-020.

**Priority:** P0 · **Size:** M · **Depends on:** RTE-007

**Implementation:** Mark a genuine eligible Agent/Task/spawn_agent as a new child task with unique tool ID.

**Acceptance / evidence:** Exactly one routed assessment per child; unrelated tool calls never trigger Jev.

### RTE-020 — Implement concurrency-safe decision dedupe

**Status:** done · Evidence: `../evidence/p1/state-native-preflight.json`; 26 persistent-state tests, cross-process at-most-once and scope isolation. Integrated into primary local main (uncommitted).

**Priority:** P0 · **Size:** M · **Depends on:** RTE-018,RTE-019

**Implementation:** Use per-event key and bounded private store; atomic writes and concurrent hook tolerance.

**Acceptance / evidence:** Parallel spawn stress suite shows no swapped decisions or duplicate requests.

### RTE-021 — Implement root-only capability gap warning

**Status:** done · Evidence: `18_ROOT_ADVISORY.md`, root presentation/concurrency tests, `../evidence/p1/codex-root-advisory-app-server.json` and later actual fixture TUI warning rendering; no root mutation. Installed-package/full TUI and desktop behavior remain gated separately by RTE-033/RTE-048.

**Priority:** P0 · **Size:** M · **Depends on:** RTE-014,RTE-015,RTE-018

**Implementation:** Compare current model/effort with suggestion and emit once-per-task material-gain warning.

**Acceptance / evidence:** Root never changes; warning is visible, properly deduped and honest about timing.

### RTE-022 — Add explicit preflight command/skill

**Status:** done · Evidence: `14_PREFLIGHT_AND_PRIVACY_PREVIEW.md`; read-only CLI wiring and policy recommendation tests, no task execution. Integrated into primary local main (uncommitted).

**Priority:** P1 · **Size:** M · **Depends on:** RTE-012,RTE-014,RTE-015

**Implementation:** Provide CLI read-only route assess for before-execution human decision.

**Acceptance / evidence:** Running preflight prints recommendation without starting work or changing host config.

### RTE-023 — Implement state refresh on resume and compaction

**Status:** done · Evidence: `../evidence/p1/state-native-preflight.json`; lifecycle/reset/root-observation fixtures, warning preservation and dedupe. Live resume matrix remains separate. Integrated into primary local main (uncommitted).

**Priority:** P1 · **Size:** M · **Depends on:** RTE-018,RTE-020

**Implementation:** Invalidate ambiguous task state, preserve bounded dedupe, update detected parent model.

**Acceptance / evidence:** Resume/compact fixture does not misattribute a prior model or spam warnings.


## P4 — Claude adapter

### RTE-024 — Integrate Claude UserPromptSubmit advisory

**Status:** done · Shared-core interactive CLI2.1.303 supplies SessionStart model;
real native warning shown, two turns completed, one classification/warning and
zero additional calls on `sim`; root Haiku5.5/Medium unchanged. Evidence:
`21_CLAUDE_OBSERVATIONS_AND_ROOT_LIMIT.md`, `../evidence/p1/claude-root-interactive-native.json`.
Earlier missing model was measured in `-p` print mode, which still degrades;
desktop and packaged integration remain separate required gates. Local main,
uncommitted.

**Priority:** P0 · **Size:** M · **Depends on:** RTE-018,RTE-021

**Implementation:** Replace unconditional classification and upstream autoswitch with gated root advice.

**Acceptance / evidence:** Only new root tasks invoke Jev; current Claude model and effort never mutated.

### RTE-025 — Integrate Claude PreToolUse worker route

**Status:** done · Evidence: `../evidence/p1/claude-core-native.json`; actual Haiku worker through core/policy/state; pins/custom no-op unit fixtures. Full coexistence matrix remains RTE-047. Integrated into primary local main (uncommitted).

**Priority:** P0 · **Size:** L · **Depends on:** RTE-003,RTE-016,RTE-019

**Implementation:** Mutate only verified Agent/Task spawn fields, respecting overrides and other hooks.

**Acceptance / evidence:** Live unpinned worker runs under chosen model; pins/custom agents no-op.

### RTE-026 — Determine supported Claude worker effort semantics

**Status:** done · Evidence: `../evidence/p1/claude-core-native.json`; actual child Medium with unchanged parent High. Only the verified CLI primitive is enabled in bootstrap. Integrated into primary local main (uncommitted).

**Priority:** P1 · **Size:** S · **Depends on:** RTE-003,RTE-015

**Implementation:** Probe Agent schema and custom agent profile capabilities; implement only approved method.

**Acceptance / evidence:** Verified effort behavior or explicit documented unsupported/advisory status.

### RTE-027 — Wire Claude plugin hooks, settings and no-autoswitch

**Status:** done · Self-contained native exec-form package, strict native
validation and isolated install/disable/uninstall registration lifecycle passed;
actual installed-cache hook execution and emergency-disable state immutability
verified. No legacy autoswitch modules copied. Evidence:
`25_CLAUDE_PACKAGE_AND_ROLLBACK.md`, `../evidence/p1/claude-package-native.json`.
Claude production worker conflict-profile support remains required in RTE-047;
packaging does not grant rewrite authority. Native retained an unregistered
version cache; no false purge claim. Local main, uncommitted.

**Priority:** P1 · **Size:** M · **Depends on:** RTE-024,RTE-025

**Implementation:** Register hooks through fork plugin packaging; preserve installed binary and custom config.

**Acceptance / evidence:** Fresh Claude plugin install and disable/uninstall restore baseline.

### RTE-028 — Observe Claude effective child route and model switches

**Status:** done · Evidence: `21_CLAUDE_OBSERVATIONS_AND_ROOT_LIMIT.md`, `../evidence/p1/claude-telemetry-native.json`, native-format switch/unit fixtures. Actual shared-core CLI child logs separate requested Haiku/Medium from actual child-model unknown / effort host-reported; matching scoped start/stop identity, no parent-tool join. PostModelSwitch producer reports to_model, unknown effort, no mutation. Live manual-switch/desktop/coexistence remain later integration gates. Primary local main, uncommitted.

**Priority:** P1 · **Size:** M · **Depends on:** RTE-025

**Implementation:** Use supported agent lifecycle/host output and switch events to collect available truth.

**Acceptance / evidence:** Decision logs distinguish requested model from verified/reported/unverified actual.

### RTE-029 — Claude live integration tests

**Priority:** P0 · **Size:** M · **Depends on:** RTE-024,RTE-025,RTE-027,RTE-028

**Implementation:** Test Claude CLI and local Desktop Code sessions: root Sonnet/Opus, pins, generic eligibility, permissions and concurrent workers; capture per-surface evidence.

**Acceptance / evidence:** Record terminal evidence and pass documented smoke matrix; regressions identified.

### RTE-047 — Test Claude hook coexistence and conflict policy

**Priority:** P1 · **Size:** M · **Depends on:** RTE-025,RTE-027

**Implementation:** Install alongside other PreToolUse hooks, detect possible competing rewrite and document mitigation.

**Acceptance / evidence:** No assumption of undocumented merge order; ambiguous conflicts disable auto selection.


## P5 — Codex adapter

### RTE-030 — Implement Codex PreToolUse spawn adapter

**Status:** done · Evidence: `../evidence/p1/codex-core-native.json`, `15_CODEX_CORE_NATIVE_EVIDENCE.md`; actual Luna/Medium child via shared preparation/MCP/policy/state/native core, parent and sandbox unchanged; pins/custom no-op native-format fixtures. Full live permission/coexistence/desktop matrix remains RTE-033/038/048. Integrated into primary local main (uncommitted).

**Priority:** P0 · **Size:** L · **Depends on:** RTE-004,RTE-016,RTE-019

**Implementation:** Use native hook for model+effort argument rewrite only when verified schema supports both.

**Acceptance / evidence:** Actual unpinned child resolves correct model+effort; pinned child unchanged.

### RTE-031 — Implement Codex UserPromptSubmit root advisor

**Status:** done · Evidence: `18_ROOT_ADVISORY.md`, `../evidence/p1/codex-root-advisory-app-server.json`; official native model/turn metadata, boundary-gated shared adapter and nonblocking warning entry observed. Installation/production-launcher smoke remains RTE-032/RTE-033; no effort inferred when native metadata omits it.

**Priority:** P0 · **Size:** M · **Depends on:** RTE-018,RTE-021

**Implementation:** Read official active model hook metadata and warn on new root tasks without changing config.

**Acceptance / evidence:** No root model/effort mutation; continuation suppresses Jev.

### RTE-032 — Implement Codex plugin manifest and trust workflow

**Progress (not done):** `19_CODEX_PACKAGE_AND_TRUST.md`; self-contained content-versioned builder and actual isolated CLI install/disable/uninstall/marketplace removal passed (`../evidence/p1/codex-package-native.json`). Native trust and positive packaged-hook execution remain required; no main-user installation or desktop claim.

**Priority:** P1 · **Size:** M · **Depends on:** RTE-030,RTE-031

**Implementation:** Package hooks via current plugin schema and private data directory; document trust steps.

**Acceptance / evidence:** Install/trust/disable/uninstall pass on clean sandbox without patching codex binary.

### RTE-033 — Codex live integration and compatibility tests

**Priority:** P0 · **Size:** M · **Depends on:** RTE-030,RTE-031,RTE-032

**Implementation:** Test CLI/native spawn with valid/invalid catalog, effort and custom profile overrides.

**Acceptance / evidence:** Host actually runs selected child; logs prove root unchanged and permissions preserved.

### RTE-048 — Test Codex plugin compatibility across surfaces

**Priority:** P0 · **Size:** M · **Depends on:** RTE-032,RTE-033

**Implementation:** Verify Codex CLI and local desktop plugin environments as mandatory surfaces; check hook loading/trust, credentials, visible warnings, effective worker model/effort and permissions.

**Acceptance / evidence:** Both CLI and desktop have observed passing smoke evidence; unsupported required capability blocks release, not silently downgraded to optional.


## P6 — Tests and evaluation

### RTE-034 — Build unit/property/contract test suite

**Status:** in_progress · Offline properties and SDK-required CI job implemented;
local 673-test suite passed on Python 3.11 with SDK/no-SDK cells. Actual remote
unit/contract CI green remains unverified; no commit/push authorized. Evidence:
`23_OFFLINE_CONTRACT_SUITE.md`, `../evidence/p1/offline-contract-suite-local.json`.

**Priority:** P0 · **Size:** L · **Depends on:** RTE-016,RTE-018,RTE-020

**Implementation:** Property-test precedence, deterministic normalization, state isolation, no-op fallbacks.

**Acceptance / evidence:** Unit/contract CI green with failed-provider and unsupported-version fixtures.

### RTE-035 — Build representative boundary and routing fixture corpus

**Status:** done · Evidence: `../evidence/p1/boundary-corpus-eval.json`; 62 tasks, 34 multi-user-turn sequences/83 events, documented provenance. One conservative mismatch disclosed; not held-out quality. Integrated into primary local main (uncommitted).

**Priority:** P0 · **Size:** M · **Depends on:** RTE-018,RTE-014

**Implementation:** Curate labeled new vs continuation vs ambiguous, task tier, risk and effort cases.

**Acceptance / evidence:** At least 60 diverse labeled task cases and 30 multi-turn sequences, documented provenance.

### RTE-036 — Implement full shadow-mode telemetry

**Status:** done · Evidence: `20_PRIVACY_SAFE_TELEMETRY.md`, `../evidence/p1/privacy-safe-telemetry-core.json`, `../evidence/p1/codex-package-telemetry-native.json`; strict private bounded JSONL, requested/recommended versus host-reported actual, hashed IDs, classification/activity producers and fail-open behavior. 26 focused tests; full suite620 (pinned SDK no skips). Core shadow acceptance met; trusted package execution, live Claude observation, desktop and latency remain separate gates. Primary local main, uncommitted.

**Priority:** P1 · **Size:** M · **Depends on:** RTE-017,RTE-020

**Implementation:** Write structured privacy-safe JSONL for classifications, recommendations and actual if available.

**Acceptance / evidence:** Zero argument mutation; logs parsable; raw prompts off by default.

### RTE-037 — Benchmark AA priors and alternatives

**Status:** in_progress · Four-strategy actual synthetic code-review outcome
pilot published: 24 task executions, six parent selections, six Jev callbacks.
All Jev assessments abstained/fell back; no efficacy claim for unselected routes.
Three self-authored tasks do not establish accepted-code/test quality, human
rework or representative uncertainty. Full benchmark remains required. Evidence:
`28_TASK_OUTCOME_PILOT.md`, `../evidence/p1/task-outcomes-pilot.json`.
Actual code-generation slice now also published: 24 implementations, 120 frozen
test-method executions in isolated offline containers, all passing. Evidence:
`29_CODE_OUTCOME_SLICE.md`, `../evidence/p1/code-outcomes-synthetic.json`.
Still not representative human acceptance/native child/Codex/desktop proof.

**Priority:** P1 · **Size:** L · **Depends on:** RTE-035,RTE-036

**Implementation:** Compare base heuristics, Jev policy, and parent selection on matching real tasks.

**Acceptance / evidence:** Publish success/retries/latency/quota proxy data and confidence intervals; no fake savings.

### RTE-038 — Verify security and approval boundaries

**Status:** done · Shared-core threat model, adversarial fixture acceptance and
scoped native read-only/never regression verified; two medium defects fixed and
independently rechecked. Evidence: `24_SECURITY_AND_APPROVAL_BOUNDARIES.md`,
`../evidence/p1/security-boundaries-local.json`,
`../evidence/p1/codex-security-regression-native.json`. Unsupported/unverified
native modes, desktop and other-hook coexistence remain separate release gates;
not a full scanner certification. Local main, uncommitted.

**Priority:** P0 · **Size:** M · **Depends on:** RTE-025,RTE-030

**Implementation:** Threat-model shell escaping, prompt exfiltration, permissionDecision allow, config injection and hook conflicts.

**Acceptance / evidence:** No secret leaks in fixtures; approvals/sandbox unaffected outside target spawn calls.

### RTE-039 — Measure classification and UX overhead

**Status:** done · Paired root-core before/after/logging measurements and actual
20-call synthetic production JevClient sample published; 0 callbacks on obvious
continuations/duplicate deliveries. Measurement exposed and repaired actual SDK
worker import shadowing. Evidence: `27_CLASSIFICATION_AND_LOCAL_OVERHEAD.md`,
`../evidence/p1/classification-overhead-local.json`. Root-only local overhead is
not native/desktop or task-completion latency; full matrices and benchmarks stay
separate. Local main, uncommitted.

**Priority:** P1 · **Size:** M · **Depends on:** RTE-024,RTE-031,RTE-036

**Implementation:** Measure p50/p95 Jev, number of calls per task, log overhead and warning frequency.

**Acceptance / evidence:** Document before/after latency and ensure obvious continuations incur zero Jev calls.

### RTE-040 — Check prompt-cache and quota assumptions

**Priority:** P1 · **Size:** M · **Depends on:** RTE-029,RTE-033,RTE-037

**Implementation:** Measure parent model stability, cache-related events if supported and usage proxies.

**Acceptance / evidence:** No unsupported claims about cache hit rates or subscriptions; report only measured proxies.


## P7 — Release

### RTE-041 — Document two-runtime installation and rollback

**Priority:** P0 · **Size:** M · **Depends on:** RTE-027,RTE-032

**Implementation:** Write fresh install, mode switching, trust, privacy setup, diagnostic and uninstall guides.

**Acceptance / evidence:** Independent users can remove both adapters with CLI behavior restored.

### RTE-042 — Create diagnostic and explain tools

**Status:** done · Evidence: `22_OFFLINE_EXPLAIN.md`, `../evidence/p1/explain-offline-core.json`, `../evidence/p1/explain-offline-native-format.json`. Explicit scoped historical records, reasons/provenance and hash-bound saved catalog/policy controls; no reclassification/runtime/key/config/stdin access or state/lock/cache writes. 23 focused explain tests, relocated package CLI proof; full658pass (pinned SDK no skips). Diagnostic metadata/profile tool remains separate. No actual tool-child join/current entitlement inferred. Primary local main, uncommitted.

**Priority:** P1 · **Size:** M · **Depends on:** RTE-028,RTE-036

**Implementation:** Read recorded decision and catalog status; report degraded support without reclassifying.

**Acceptance / evidence:** Explain works offline and outputs provenance, reason and actual/unverified status.

### RTE-043 — Wire CI and compatibility/version gates

**Priority:** P0 · **Size:** M · **Depends on:** RTE-034,RTE-029,RTE-033

**Implementation:** Add automatic unit/contract suite and optional live matrix jobs for version changes.

**Acceptance / evidence:** CI rejects unsupported field mutations and missing rollback checks.

### RTE-044 — Perform staged rollout and release gate

**Priority:** P0 · **Size:** M · **Depends on:** RTE-037,RTE-038,RTE-039,RTE-041,RTE-043,RTE-048

**Implementation:** Enable one runtime at a time after shadow pilot; document known gaps and decisions.

**Acceptance / evidence:** Sign-off checklist and measured report exist; user can disable instantly.

### RTE-045 — Update in-repo ADR and policy tuning guide

**Priority:** P1 · **Size:** S · **Depends on:** RTE-037,RTE-044

**Implementation:** Explain task boundary trade-offs, model effort policy and reproducible score updates.

**Acceptance / evidence:** No hardcoded outdated model ID presented as universally available.

---

## Mandatory gate checks

- **Gate G0:** `RTE-003` and `RTE-004` produce real host evidence before claiming automatic child routing.
- **Gate G1:** all catalog and override safety `P0` items pass before any `auto_workers` enablement.
- **Gate G2:** both `RTE-029` and `RTE-033` are demonstrated on official installed binaries.
- **Gate G3:** no root model/effort change, no unauthorized rewriter, no secret exfiltration in tests.
- **Gate G4:** default installation mode is shadow/disabled until explicit opt-in; rollback works.

## Suggested milestones / PR slicing

1. PR-Audit: RTE-001…006, with short decision memo and evidence.
2. PR-Core: contracts, catalog, classifier, privacy (RTE-007…017, 046).
3. PR-Boundary: state + warnings + preflight (RTE-018…023).
4. PR-Claude: adapter + smoke + coexistence (RTE-024…029, 047).
5. PR-Codex: adapter/plugin + smoke (RTE-030…033, 048).
6. PR-Eval-Release: tests, evals, security, docs, CI (RTE-034…045).

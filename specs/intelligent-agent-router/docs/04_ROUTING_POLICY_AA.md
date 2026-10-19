# 04 — Routing Policy and Artificial Analysis Research Ledger

## 1. Operating principle

**Jev estimates task requirements; the policy chooses an available model and reasoning effort.** These must not be conflated. Optimize successful completion rate and quality-adjusted throughput, not simply minimum per-token price. Task risk, correctness verifiability, tool support and explicit pins outrank cost and speed.

This policy is a **starting prior** informed by our previous Artificial Analysis comparisons. It is not a verified current leaderboard, not a guaranteed model hierarchy, and not an estimate of how much of a flat subscription quota a given route consumes. Revalidate both scores and model IDs before deployment.

## 1.1 Required target versions (user refinement, 2026-10-19)

These are **desired model versions**, not verified runtime IDs or evidence of account access:

| Runtime | Family | Required target version |
|---|---|---|
| Claude Code | Fable | **5.1** |
| Codex | Luna | **6** |
| Codex | Terra | **6** |
| Codex | Sol | **6.1** |
| Codex | Astra | **6** |

The existing Sonnet 5.5 and Opus 5.5 candidates remain unchanged. This refinement does not newly fix a Haiku version. Family labels in diagrams and tier maps are policy keys only, not executable model IDs. In particular, `terra` means the desired **Terra 6** candidate, not the historical Terra 5.6 benchmark entry below.

Account availability of the target models is **assumed by explicit user instruction (2026-10-19)**, recorded as `availability_source: user_assumption`. This removes entitlement discovery as a prerequisite, but does not verify runtime IDs or effort/schema support.

The registry must keep `family`, `target_version`, `runtime_model_id`, account/surface and verification evidence separate. Resolve a target only through a supported runtime identifier whose mapping to that exact version has been verified. A moving alias is insufficient without version evidence and invalidation when the mapping changes. Unknown or mismatched version => no automatic route to that candidate (`target_version_unverified` or `target_version_unavailable`); preserve native inputs when no valid route remains. Never silently replace a target with another generation or invent an ID. Enabling a different target version requires an explicit policy/configuration change.

These pins apply to router-selected candidates and recommendations, not to the user's root session or explicit worker overrides. They do not enable frontier routing, change effort defaults or bypass availability/opt-in checks.

## 2. Suggested task taxonomy

| Class | Description | Default constraints | Escalation triggers |
|---|---|---|---|
| T0 mechanical | narrow read/search/extract/rename/lint | fastest adequate available worker; lightweight reasoning | ambiguous work, edits with blast radius, secrets |
| T1 standard | bounded features, unit tests, refactor with known contract | balanced or strong-efficient medium effort | unfamiliar code, multi-module behavior, unreliable tests |
| T2 difficult | diagnosis, concurrency, nontrivial API design, deep review | strong model, high effort where supported | unbounded ambiguity, high safety impact |
| T3 frontier | open architecture, large migrations, strategic/long-horizon reasoning | frontier opt-in, high; only higher effort when measured benefit | unusual risk / low verifiability / repeated failure |

`criticality`, `verifiability`, `context_demand`, `parallelizability` are **orthogonal attributes**, not just synonyms for high complexity. An authentication patch may be short yet high-risk.

## 3. Claude candidate ladder (subject to catalog)

- **Haiku (T0):** quick extraction, obvious search, mechanical transformation; little/no reasoning effort if model does not expose it.
- **Sonnet 5.5 (T1 / some T2):** standard implementation, bounded refactoring, tests, frontend and many routine coding tasks. Medium effort initially; High only for enough expected quality gain.
- **Opus 5.5 (T2 / some T3):** unknown-cause debugging, intricate architecture, security/migration/concurrency, critical review; Medium/High as a deliberate efficiency/quality tradeoff.
- **Fable 5.1 (T3 opt-in):** rare exceptionally complex/long-context tasks; gate behind explicit availability, quota and user opt-in. Do not infer Fable means automatically better at every workflow.

**Important:** Claude agent tool schema may expose model only, not a per-agent reasoning-effort override. The policy can still recommend effort, but only apply it through an officially supported runtime mechanism; log `effort_advisory_only` otherwise.

## 4. Codex candidate ladder (subject to catalog)

- **Luna 6 (T0):** very fast/cheap lightweight workers, lookups, simple transformations. Use valid low/medium effort if supported.
- **Terra 6 (T0/T1):** low-latency small edits / mid-tier work; assess actual coding performance and relative cost against Luna and Sol.
- **Sol 6.1 Medium (T1/T2):** good default for serious standard coding and development; choose Medium first.
- **Sol 6.1 High (T2):** architectural coding, subtle debugging, complex review. Upgrade effort before changing model when model change has greater latency/quota/cache overhead.
- **Sol 6.1 XHigh/Max (rare):** benchmark-driven only when additional effort demonstrably improves completion; do not escalate merely because a task is long.
- **Astra 6 High (T3):** frontier architectural reasoning / exceptionally difficult system decisions; use only with opt-in policy where constrained by quota and availability.

Treat the **verified runtime catalog** as authoritative for availability and identifier resolution, while preserving the explicit target versions in §1.1. A newer catalog entry does not automatically upgrade the configured target. The same generic `sol` alias may refer to different versions over time; never assume it satisfies Sol 6.1 without evidence.

## 5. Prior research: evidence ledger (historical, not verified live)

Historical version labels remain unchanged: Terra 5.6 measurements are **not** Terra 6 measurements and cannot be relabeled or assumed transferable.

These are **notes retrieved from our earlier model-comparison conversations**, included to seed benchmark hypotheses. They were not independently remeasured for this ZIP. Do not code them as static facts without verifying source dates, definitions, model versions and metric methodology.

| Research snapshot / observation | Historical numbers / finding | What it implies | Caution |
|---|---|---|---|
| AA comparison of medium-effort models (Oct 2026 prior conversation) | Haiku 5.5 Medium: Intelligence 34, ~$0.05/task, ~119s; Sonnet 5.5 Medium: 41, ~$0.48/task, ~140s; GPT-6.1 Sol Medium: 48, ~$0.21/task, ~167s | Medium often efficient; Sonnet/Haiku strong throughput for scoped tasks | AA Intelligence Index != coding-agent score; prices are API benchmark costs |
| AA High effort snapshot | Haiku 38/~$0.08; Sonnet 47/~$0.88; Sol 50/~$0.32 | Higher effort may improve index while increasing cost | Cross-model comparisons confounded by task distribution and harness |
| Smaller Codex model comparison | Terra 5.6 Medium index 30/~$0.18/~55s; Luna 6 Medium index 30/~$0.02; High 34/~$0.34 and 33/~$0.03 respectively | Luna as lightweight; Terra as speed candidate | Versions/time must be rechecked; no inference about subscription quota |
| Our later strategic comparisons | Sol High vs Astra High had narrower capability differences than initial expectations, with Sol potentially lower task cost; higher thinking sometimes adds tools/time | Default Sol High for many complex tasks; Astra when justified | No precise cross-version margin independently confirmed |
| Sonnet 5.5 vs Opus 5.5 | Sonnet can do well on selected agentic coding benchmarks despite lower aggregate index; Opus is valuable for judgement/ambiguity | Avoid blanket “Opus for all code” | Agent benchmark results depend on harness, eval and effort |
| Composer 2.5 Fast | Strong throughput on well-scoped execution; GPT-5.6 Medium potentially higher aggregate reasoning capability at comparable per-task cost | Consider as *external* efficiency reference only | Composer is not necessarily a model choice reachable from official Claude/Codex auth |
| Fable vs Opus | Fable may offer coding throughput advantages in selected evaluations; top-model usage economics complex | Opt-in frontier route, measure locally | Availability/licensing/usage must be checked |

**Do not use the previous handoff's unsourced “one universal index/time/cost table” as production policy.** Snapshots may refer to different model generations, intelligence-index versions and benchmark measurement protocols.

## 6. Policy interface, calibration, and conservative thresholds

The following are proposed defaults to calibrate, **not data-derived claims**:

- `confidence_min_auto = 0.75`: below this, retain native inheritance (`defer`) instead of blindly choosing cheaper/stronger.
- `root_warning_min_gain = material`: emit only when expected success/quality difference is clinically meaningful for the task; do not treat raw index delta of 1–2 as automatic reason to warn.
- `frontier_opt_in = false`: Fable/Astra selected automatically only when user opts in, account supports them and policy approves.
- `high_risk_floor`: critical security/financial/destructive code review should not be downgraded solely to save tokens; demand adequate tests/review.
- `max_router_wall_ms = 2500` candidate; lower after measuring Jev latency.
- `on_low_confidence = inherit`, `on_error = inherit`, `on_unknown_catalog = inherit`.

An **evaluation-derived** policy may eventually use per-category quality estimates, confidence intervals and expected retries rather than ordinal tiers. Keep configuration flexible enough to replace rank heuristics with measured models.

### Optimization objective (conceptual)

Among candidates exceeding `minimum_quality(task)` and constraints, minimize:

`E[time_to_accepted_change] + λ * E[usage_or_API_cost] + μ * E[retry_or_escalation] + ν * cache_switch_penalty`

Estimate expected values empirically; do not fabricate costs. Use a lexicographic safety/capability floor before applying weighted optimization. Use `cost/task` and success rate only from comparable runs.

## 7. Effort selection is independent

- T0: lowest reliably supported effort with adequate accuracy.
- T1: Medium default for Sol/Sonnet if supported.
- T2: High after checking model-specific support and latency.
- T3: High by default; XHigh/Max only when a representative eval supports the escalation.
- Prefer `same_model + higher_effort` over a **model switch** for root advice when it gives nearly the same benefit, especially with a warm context; actual switching is always the user's choice.
- Effort is not universally ordered across providers; e.g., “High” on two models does not imply comparable reasoning compute.

## 8. Recalibration tasks

1. Retrieve current AA model reports with dates, version IDs and methodology; snapshot raw evidence separately from routing tables.
2. Derive an **availability/capability registry** from each runtime account; never code broad tier aliases as actual IDs.
3. Build 40–80 labeled routing cases across code tasks, including cases with identical apparent length but different risk.
4. A/B the original heuristic fork, Jev-based router, and root/orchestrator's own explicit model selection.
5. Score `successful_change`, `human_rework`, `latency`, `tool_calls`, `number_of_classifier_calls`, `model/effort`, and approximate quota pressure.
6. Update routing policy only after target performance confidence. Version policy and roll back on regressions.

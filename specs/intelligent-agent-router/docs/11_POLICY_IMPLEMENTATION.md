# Deterministic policy v1.0.0 — incremental implementation

`router_core/policy.py` separates provider requirements from model/effort selection. The 28 expectations in `tests/fixtures/intelligent-router/policy-golden.json` were authored before implementation. They are **synthetic policy fixtures**, not a current model leaderboard or installable catalog. IDs prefixed `fixture-` are fake. Supported model mappings must come from independent trusted inventory evidence.

## Ordering and constraints

1. Explicit non-null model/effort, including empty strings, and custom/unknown profiles skip before privacy/provider work. Verified generic-type routing can also be disabled.
2. Disabled mode skips; warn mode does not classify or route workers; shadow may assess but only records recommendations and never selected route fields. Explicit preflight has a separate enable switch. Root continuation/unknown boundary never calls the provider.
3. Unknown task binding, unavailable version/surface/tool catalog or absent consent preserves native input. Real tasks cannot be relabeled synthetic: only exact registered fixtures pass synthetic consent.
4. Provider failure/absence, abstain, unknown risk or confidence below the configured threshold defers. No heuristic model selection substitutes for a failed provider response. Callback exceptions are converted to sanitized failure metadata.
5. Hard capability floor uses the provider tier plus orthogonal high risk and high complexity/reasoning/tool/ambiguity signals. High risk has a minimum T2 model and High effort. High scores cannot be contradicted by a coarse T0 tier. T3 requires frontier opt-in; absent opt-in defers rather than downgrading.
6. Select only exact enabled family/version mappings for this runtime, host version, surface and native tool. Haiku has no user-fixed generation; only one verified scoped generation may be selected. No arbitrary moving-alias choice or silent target generation substitution.
7. Choose effort independently, after candidate support: T0 Low or supported Medium, T1 Medium (High for heavier reasoning/ambiguity), T2/T3 High. XHigh/Max are not automatically selected without measured benefit. Unsupported effort yields advisory-only or a supported adequate peer, never an unsupported selected field or implicit effort inheritance.
8. Ordinary root warnings require a known actual root mapping and an ordinal capability gap or supported higher effort on the same model. Unknown current effort prevents an effort-only warning. Stronger roots are never advised to downgrade. All root/preflight results contain recommendation fields only; selected worker route fields are forbidden by the contracts.

Explicit user preflight works before a root session exists: it recommends a supported route without claiming to have detected a gap against an unknown root. Policy does not implement visible warning output or warning dedupe yet. Those remain separate adapter/state work.

## Prior, not empirical optimizer

Default candidate preference: Claude Haiku → Sonnet → Opus for mechanical work, Sonnet → Opus for standard, Opus for difficult, Fable for opt-in frontier. Codex Luna → Terra → Sol for mechanical, Sol → Terra for standard, Sol for difficult, Astra for opt-in frontier. Fallbacks never cross the hard floor. These orders are explicit initial priors from the plan, not verified success, cost, latency or subscription-quota estimates. Release evaluation must measure representative task outcomes and tune the policy rather than claim fabricated savings.

## API and verification

`decide(envelope, provider_result, catalog, config, scope)` is pure. `assess(envelope, classify_callback, catalog, config, scope, boundary_is_new=...)` performs cheap guards and consent/minimization before at most one callback. It never executes a task or edits arguments/settings. Persistent exactly-once/dedupe must wrap it; repeated separate calls are not deduped by this function.

Nine policy test methods include 28 named golden cases, a 384-case runtime/tier/risk/confidence/mode matrix, callback counters for zero-call guards, unsupported-scope checks, and explicit preflight. This is deterministic unit evidence, not live production-adapter or desktop routing proof.

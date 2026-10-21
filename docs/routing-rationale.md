# Benchmark-informed routing rationale

**Artificial Analysis informs the policy; it does not validate the router.**
Jev estimates task requirements. A separate local policy chooses a compatible
model and reasoning effort, subject to risk, explicit user choices and runtime
support. The goal is successful completion with appropriate resource use—not the
lowest token price or the strongest model for every task.

## What the benchmarks tell us

[Artificial Analysis](https://artificialanalysis.ai/methodology) publishes model,
agent, performance and price evaluations. They provide useful starting priors
for considering capability, speed and resource trade-offs, not a universal
routing rule.

- **Intelligence is not coding-agent performance.** The
  [Intelligence Index methodology](https://artificialanalysis.ai/methodology/intelligence-benchmarking)
  describes a broad capability composite. Its aggregate is not a probability that
  a model will fix a bug in your repository.
- **The agent and its settings matter.** The separate
  [Coding Agent Index methodology](https://artificialanalysis.ai/methodology/coding-agents-benchmarking)
  evaluates end-to-end software engineering. It treats agent variants, including
  reasoning settings, as distinct entries. Repository Q&A, implementation and
  terminal tasks need not favor the same choice. A result belongs to the tested
  agent configuration, not just a model family name.
- **API cost is not subscription quota.** AA's
  [metric definitions](https://artificialanalysis.ai/methodology#definitions)
  derive Cost per Task from token usage and API prices. That does not establish
  how much of a flat-rate coding subscription a route consumes. Its estimated
  Intelligence Index Time per Task is also not a measurement of this router's
  end-to-end latency.

These distinctions motivate a task-aware policy. They do not prove that its
particular tier boundaries, thresholds or model ordering are optimal.

## How the policy uses those priors

The intelligent routing core groups work into broad requirement tiers:

| Tier | Typical work | Policy starting point |
|---|---|---|
| T0: mechanical | Narrow extraction, lookup or deterministic transformation | Lightweight eligible candidate; low effort, or medium if low is unsupported. |
| T1: standard | Bounded implementation, tests or refactoring with a clear contract | Balanced candidate; medium effort unless reasoning or ambiguity calls for high. |
| T2: difficult | Uncertain diagnosis, complex review or consequential cross-module reasoning | Strong candidate and high effort. |
| T3: frontier | Exceptionally demanding reasoning | Frontier candidate only with explicit policy opt-in; high effort. |

These are **policy priors**, not benchmark-derived guarantees. Classification is
an estimate, not a measured success probability. Low confidence, missing risk
information or an abstention leads to deferral rather than a forced choice.

### Model and effort are separate decisions

Model selection asks which eligible capability family fits the requirements.
Effort selection asks which supported reasoning setting fits those requirements.
A stronger model does not automatically require maximum effort; a long prompt
alone does not justify escalation. The core does not automatically choose
`xhigh` or `max`.

The policy resolves model support before choosing effort. If the required effort
cannot be applied, it tries an adequate supported candidate or defers with
model-only advice. It never presents an unsupported effort recommendation as an
applied setting. Effort labels should not be assumed to represent equal compute
across models or runtimes.

### Risk floors come before efficiency

A short task can still affect authentication, money or destructive operations.
The core raises high-risk work to at least the difficult tier; strong complexity,
reasoning, tool-complexity or ambiguity signals can also raise a coarse tier.
Those floors take precedence over choosing a lightweight candidate. They do not
replace authorization, tests, independent review or human judgment.

Explicit model/effort choices and custom or unknown worker profiles bypass
automatic selection. Root-session decisions are advisory: this policy does not
switch the user's active root model or effort.

### A benchmark label is not an executable model ID

Every candidate must resolve through the runtime catalog for the exact target
version, runtime surface, host version, tool and supported effort. A family name
or moving alias is insufficient evidence of that mapping. An unknown or
mismatched mapping cannot become an automatic route; a newer catalog entry does
not silently upgrade the configured target.

Mapping evidence and availability are separate. A catalog may explicitly record
availability as a user assumption rather than observed entitlement. Benchmark
coverage proves neither account access nor runtime compatibility.

## Evidence boundary and provenance

Primary-source pages were checked on **2026-10-21 UTC (2026-10-20 in São Paulo)**:

| Source | Observed scope | Use here |
|---|---|---|
| [AA Intelligence Benchmarking](https://artificialanalysis.ai/methodology/intelligence-benchmarking) | Page labeled Intelligence Index v4.3.2 | Distinguish broad capability from task-specific coding success. |
| [AA Coding Agent Benchmarking](https://artificialanalysis.ai/methodology/coding-agents-benchmarking) | Page labeled Coding Agent Index v1.5 | Distinguish agent variants and software-engineering evaluations. |
| [AA Benchmarking Methodology](https://artificialanalysis.ai/methodology) | Metric definitions as accessed on the date above | Distinguish API costs and estimated benchmark time from subscription usage and router latency. |

These are mutable source pages, not frozen leaderboard snapshots. No per-model
score, price, rank or effort-specific performance claim is asserted here.
Historical comparison notes informed the starting policy, but their numerical
claims are not republished as verified evidence or transferred to newer model
versions.

Benchmark task distributions, harnesses, tools, budgets and scoring can differ
from a real repository workflow. They do not establish router accuracy, accepted
change quality, quota savings or a universally best route. Policy defaults remain
heuristics requiring task-specific validation. This project is not endorsed by
or affiliated with Artificial Analysis.

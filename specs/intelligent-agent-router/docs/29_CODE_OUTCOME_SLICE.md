# Actual code-generation slice (RTE-037 still in progress)

This slice generates and **tests actual Python implementations**, rather than
scoring classifier agreement or only reviewing structured answers.

## Frozen tasks and safe execution

`scripts/spikes/code_tasks.py` defines three self-authored synthetic engineering
contracts: Unicode tag normalization, closed interval merging, and deterministic
topological scheduling batches. Each has five independent unittest methods,
including malformed inputs, immutability, boundary cases and 100–200 seeded
property cases. Reference implementations passed all methods; deliberately
broken seeds failed **before any model invocation**. Tests/reference were not
included in model prompts. No test was tuned after seeing generated solutions.

Generated source is never imported/evaluated by the host. The trusted grader
runs in an already-cached immutable Python image, with `--pull=never`, no network,
read-only root and fresh bundle mount, nonroot UID, dropped capabilities,
no-new-privileges, PID/CPU/memory limits, bounded tmpfs, timeout and output limit.
No project/home directory, Docker socket, credential or host environment is
mounted/forwarded. Every grading container is force-removed and checked absent.
The primary checkout's six native boundary probes passed (correct/incorrect,
blocked network/write, infinite loop and output flood), with no leftovers.

This is defense in depth for these synthetic tasks, **not** a hardened
multi-tenant sandbox or tamper-proof adversarial judge. Candidate and tests
share a Python interpreter. Host SIGKILL/unavailable daemon may prevent cleanup.

## Actual runs

Three tasks × four strategies × two repeats = **24 generated solutions**, all
passing exactly five frozen test methods: **120 method executions**, plus their
seeded cases. All containers were verified removed. Native reported modelUsage
Haiku/Sonnet/Opus 5.5; actual effort remains unobserved.

| Strategy | Requested executors | Passing solutions | Total wall p50 / p95 |
|---|---|---:|---:|
| Original heuristic | Opus/Medium ×6 | 6/6 | 7.82 / 13.45 s |
| Jev + production policy | Sonnet/Medium ×6 | 6/6 | 5.48 / 10.33 s |
| Actual parent selection | Haiku/Medium ×5; Sonnet/Medium ×1 | 6/6 | 11.75 / 16.91 s |
| Fixed no-router parent baseline | Sonnet/Medium ×6 | 6/6 | 6.15 / 21.41 s |

The Jev arm made six callbacks: **two** recommendations cleared the unchanged
confidence threshold (0.79/0.80), and **four** abstained (0.25–0.32). Both explicit
recommendations and all fallbacks chose the **same Sonnet/Medium executor as the
fixed baseline**. Consequently this slice does not demonstrate better routing,
lower subscription usage, or savings. No production threshold/policy was tuned.

All arms received identical generation prompts/schema. Parent selection usage
and latency include its separate selection call. Usage fields are host-observed
counters, not total quota/cost; internal retries/wire counts remain unobserved.
Human rework is `null/not_measured`, not zero. There were no orchestrator retries.

Three purposively authored tasks are too few and narrow for representative
engineering acceptance/noninferiority. Empirical clustered bootstrap ranges
degenerate to [1,1]; that is **not calibrated reliability certainty**. p95 is the
maximum of six observations, affected by concurrency and uncontrolled cache/
service effects. Direct CLI executors are not native routed child/inheritance
proof, and Claude results do not establish Codex or desktop compatibility.

## Artifacts and reproduction

- `scripts/spikes/code_outcome_benchmark.py` — explicit opt-in, four strategies,
  bounded parallel collection, fixed tests and failure-inclusive reporting.
- `scripts/spikes/code_grader.py` — immutable-image offline container grader.
- [`code-outcomes-synthetic.json`](../evidence/p1/code-outcomes-synthetic.json) —
  all 24 sources, grades, selection results, latency/usage and collection hashes.
- [`code-grader-boundaries.json`](../evidence/p1/code-grader-boundaries.json) —
  primary checkout boundary probe outcomes.

```sh
# No model, provider or credential access:
rtk "$ROUTER_PYTHON" scripts/spikes/code_outcome_benchmark.py \
  --validate-fixtures --output /tmp/router-code-fixtures.json

# Sends only the frozen synthetic descriptions to Jev:
rtk "$ROUTER_PYTHON" scripts/spikes/code_outcome_benchmark.py --run-synthetic \
  --key-file "$HOME/.config/intelligent-agent-router/jev.env" \
  --output /tmp/router-code-outcomes.json
```

Use the selected interpreter containing SDK 0.7.5 and an inspected cached Python
image ID (`--image sha256:…`); the grader never pulls. Default image ID records
this machine's existing Python 3.12 slim image, not a universal installation ID.
Full local SDK-required suite: **710 passed, zero skips**.

Post-review hardening enforces all five methods plus verified cleanup at result
acceptance, and bounds native stdout/stderr during capture (not after unbounded
allocation). The collected batch preceded these changes; every saved row was
independently checked against both conditions, with no model calls repeated.
Collection and current report source hashes are retained separately.

## Still required

RTE-037 remains **in progress**: broader representative engineering tasks,
independent human correction/rework review and defensible uncertainty; actual
native-child selection/inheritance and both runtime families. This slice does
not resolve Claude session-hook authority, desktop validation, Codex package
trust, remote CI or rollout gates.

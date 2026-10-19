# Four-strategy task-output pilot — RTE-037 remains in progress

## What was actually executed

Three newly self-authored synthetic code-review tasks (strict-positive search,
stable deduplication and binary-search boundary), two repeats, four strategies:
**24 task executions**, plus **six parent-selection executions** and **six Jev
callback attempts**. Claude Code 2.1.303; up to three independent jobs concurrent,
seeded arm order. No generated code executed or modified files. Models returned
schema-constrained bug locations and counterexamples; trusted literal oracles
independently computed correct/buggy return values. Every arm received the exact
same execution prompt/schema, without answer keys or previous outcomes.

Sources: `scripts/spikes/task_outcome_pilot.py`,
`tests/fixtures/intelligent-router/task-outcomes-pilot.json`.
Raw trials: [`task-outcomes-pilot.json`](../evidence/p1/task-outcomes-pilot.json).

| Strategy | Exact operational meaning | Oracle successes | Total wall p50 / p95 |
|---|---|---:|---:|
| A: original heuristic | Unmodified original `classify_heuristic` + default class targets; CLI tiebreak disabled | 6/6 | 7.88 / 18.50 s |
| B: Jev + production policy | Actual synthetic requirements request, unchanged 0.75 confidence gate and bootstrap catalog; fallback to parent baseline on abstention | 6/6 | 5.48 / 11.18 s |
| C: parent selection | Separate Sonnet/Medium recommendation from Haiku/Sonnet Medium candidates, then direct execution | 3/6 | 7.06 / 10.66 s |
| D: no-router parent baseline | Direct execution with fixed Sonnet/Medium, no classifier | 6/6 | 4.36 / 6.18 s |

Timing includes selection and task execution, including CLI startup, not grader
latency alone. It is not production native-subagent or desktop latency. p95 is
the maximum of six observations; concurrent service/cache effects are not
controlled. We did not rerun unfavorable samples.

## Interpretation — do not infer more than the data supports

- **B abstained on all six tasks** (normalized confidence 0.31–0.66, below 0.75).
  Every execution therefore used the same Sonnet/Medium fallback as D. This
  tests fallback safety/outcome plus classification overhead, **not the efficacy
  of any Jev-selected alternative route**. No threshold was tuned to this pilot.
- All three C failures had correct bug locations and counterexamples, but
  returned extra-quoted JSON strings where the function actually returns an
  integer/list. They remain failures under the frozen exact output contract.
  This is an output-contract failure, not proof of a reasoning deficit. Per-row
  modelUsage reports Haiku 5.5 for those executions; that association is not a
  causal model-quality conclusion.
- A requested Opus Medium/High, while B/C use the narrower measured bootstrap
  candidate catalog. Unequal available compute prevents isolating selector
  quality. No model/effort policy changes follow from this small pilot.
- Native `modelUsage` reported Haiku/Sonnet/Opus 5.5. Actual effort was **not
  observed** and is not silently equated with the requested CLI effort.

## Accounting and uncertainty

Raw data retains all 24 task trials, selection outcomes, Jev durations,
requested versus reported models, runner attempts/retries and host-exposed
usage counters. C accounting includes **both parent selection and execution**.
Missing counters are unknown, never zero. Usage counters are proxies, not
subscription quota or monetary cost. Native/provider-internal retries and wire
request counts are unobserved. Human rework is `null/not_measured`, not zero.

The report includes a seeded, task-clustered **descriptive empirical bootstrap
range**, not a calibrated reliability confidence interval. With three purposive
tasks it degenerates to [1,1] for perfect arms and [0.5,0.5] for C, because each C
task succeeded once in two repeats. Those ranges do **not** imply certainty,
noninferiority or population-level success probability. Full RTE-037 confidence
and representative-quality acceptance remains unfulfilled.

Postcollection metadata corrections (retry labels, uncertainty wording, usage
aggregation and JSON-type diagnosis) are recorded with separate collection and
report harness hashes. No native calls were repeated. The runner was hardened
to preserve launch failures as failed results; none occurred in this batch.

## Reproduction

Use the selected interpreter/venv containing pinned TypeSafe SDK 0.7.5:

```sh
rtk "$ROUTER_PYTHON" scripts/spikes/task_outcome_pilot.py --run-synthetic \
  --key-file "$HOME/.config/intelligent-agent-router/jev.env" \
  --output /tmp/router-task-outcomes.json
```

The explicit flag authorizes only these synthetic fixtures. Native runs have no
tools/MCPs, no settings sources, no session persistence and no trust bypass.
Seven focused tests cover oracles, exact JSON types, failures/fallbacks,
denominators, usage accounting and empirical ranges.

## Required next benchmark slice

RTE-037 is **not done**. Expand to representative engineering tasks with
independent accepted-code/test outcomes, repeated stochastic trials, appropriate
uncertainty and human correction/rework review. Add actual native subagent
selection/inheritance rather than confusing direct externally selected CLI
executors with those paths; cover both runtime families. Native integration,
desktop, release sign-off, cache assumptions and savings remain separate gates.

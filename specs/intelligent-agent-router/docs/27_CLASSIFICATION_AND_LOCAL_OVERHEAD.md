# Classification and local overhead (RTE-039)

## Scope and method

Measured on 2026-10-19, macOS arm64, Python 3.11.16, TypeSafe SDK 0.7.5.
Reproducible harness: `scripts/spikes/measure_overhead.py`; raw per-event timings
and paired differences: [`classification-overhead-local.json`](../evidence/p1/classification-overhead-local.json).

- **Local comparison:** 30 replicates for each of 12 arms (Claude/Codex profile ×
  disabled/shadow/warn × logging off/on). Logging pairs alternate execution order.
  Each sequence has SessionStart, one new task, duplicate delivery, four obvious
  continuations, unrelated tool call and Stop. State/logs grow across replicates,
  rather than being reset to empty for every timing. The local provider and
  model catalog are explicitly deterministic **test fixtures**, not runtime
  capability or classifier-quality evidence; zero external calls in these arms.
- **Live client:** 20 new tasks, alternating runtime adapters, using the production
  `JevClient` and the exact shipped imaginary-file-list synthetic description.
  No private project content, runtime configuration or transcript is sent.
  Each task also receives a duplicate and four continuations. The ordinary
  version-bound bootstrap catalog is used; no favorable result is injected.
- Timings surround the **entire handler**, including boundary/state/snapshots
  and telemetry writes. Percentiles use nearest rank; raw samples and counts
  are retained. Negative noisy paired differences are not clamped.
- Client wall time includes cold worker startup/import, service transport and
  normalization; credential loading is outside that timer. A fresh worker is
  launched for each classification; this is not a warmed persistent-client SLA.

## Measured results

### Real synthetic Jev client

| Metric | Observed |
|---|---:|
| Callback attempts / successful normalized results | 20 / 20 |
| Client wall p50 / p95 / maximum | 404.69 / 493.06 / 547.12 ms |
| Full new-root handler p50 / p95 | 424.17 / 509.56 ms |
| Continuation callbacks / continuation events | 0 / 80 |
| Duplicate callbacks / duplicate deliveries | 0 / 20 |
| Warnings / new tasks | 0 / 20 |
| Configured enclosing deadline | 2500 ms |

The easy live task with an adequate observed Medium root did not produce a
warning. This is an observed frequency, not a guarantee that future tasks will
need no warning. Twenty samples give descriptive percentiles, not a service SLA,
task-quality evaluation or proof of account-wide availability. Callback attempts
are known; actual wire-request count inside the SDK is **not observed**.

### Full local new-task handler (no network), milliseconds

| Profile / mode | Logging off p50 / p95 | Logging on p50 / p95 |
|---|---:|---:|
| Claude / shadow | 21.92 / 40.89 | 32.70 / 59.57 |
| Claude / warn | 27.02 / 49.65 | 44.69 / 79.45 |
| Codex / shadow | 22.53 / 41.10 | 40.52 / 75.98 |
| Codex / warn | 26.38 / 49.40 | 49.54 / 98.91 |

Disabled handler p95 was below 0.001 ms for both profiles and performed no state
or telemetry writes. This is an in-process early return, **not** total disabled
plugin process startup. Absolute paired enabled-minus-disabled sequence deltas
are in the raw artifact; these are overhead, not latency savings.

Across the **nine handler calls per sequence**, paired logging-on-minus-off p50 /
p95 added 54.13 / 111.52 ms for Claude warn and 99.81 / 205.17 ms for Codex warn.
These are percentiles of paired differences, not differences/additions of p95s.
The sequence total is a **sum of handler durations**, not elapsed user task time.

Each enabled local arm assessed exactly once per new task (30/30), with zero
callbacks on its 120 continuations or 30 duplicate deliveries. The deliberately
warning-positive fixture emitted 30/30 warnings in warn mode, zero duplicates,
and none in shadow/disabled. This controlled incidence is not an estimate of
production warning frequency. Inputs and observed root model/effort were checked
unchanged; no workers were spawned or native arguments rewritten.

Continuations are not free merely because they avoid the network: local warn
with logging enabled had continuation p95 18.50 ms (Claude), 32.15 ms (Codex).
Final log occupancy ranged from about 150–251 KB in enabled logging arms;
rotation/max-capacity steady state was **not exercised**. Both state validation
and telemetry rereads grow with retained history. These results identify a
future profiling opportunity; they do not justify weakening durability/privacy.

## Regression discovered and repaired by the measurement

The first batch returned `sdk_unavailable` for all 20 callbacks despite an
installed/importable SDK. It is preserved as
[`classification-overhead-prefixed-import-failure.json`](../evidence/p1/classification-overhead-prefixed-import-failure.json),
and must **not** be counted as service latency or successful requests.

Absolute script launch put `router_core/` first in the worker's import search.
The later-added sibling `packaging.py` shadowed the SDK's external
`packaging.version` dependency, causing a relative-import failure. Existing
in-process mocked SDK tests did not reproduce the launch environment.

The default worker now launches as `selected-python -I /absolute/_jev_worker.py`.
An actual subprocess regression uses hostile `packaging.py` and `typesafe_sdk.py`
in cwd/PYTHONPATH and distinguishes import failure from expected invalid-input
failure **before any key/client/network access**. The corrected 20-call batch
above uses that exact default worker, not an injected alternate launcher.

The pinned SDK must be installed in the **selected interpreter/venv**. Isolated
mode intentionally ignores user-site and PYTHONPATH dependencies. This is import
isolation, not a complete OS sandbox; interpreter/site-packages remain trusted.

## Reproduction and verification

Use the selected Python interpreter with pinned SDK 0.7.5 installed:

```sh
rtk "$ROUTER_PYTHON" scripts/spikes/measure_overhead.py --repeats 30 \
  --live-synthetic --live-samples 20 \
  --key-file "$HOME/.config/intelligent-agent-router/jev.env" \
  --output /tmp/router-overhead.json
```

Without `--live-synthetic` **and** `--key-file`, the default run is offline and
never reads credentials. Tests cover flag consent, payload allowlisting,
failure-inclusive distributions, callback/warning counts, immutability and
actual SDK worker import isolation. Full SDK-required suite: **692 passed,
zero skips**; strengthened hostile-import focused suite: **11 passed**.

## Not proven by this item

Native host delivery/process startup, capability-profile inventory cost, worker
routing and Codex preparation latency, desktop, human warning rendering/attention,
full task completion time, task success/retries, cache hits and subscription
savings remain outside these measurements. Native visible-warning proofs are
recorded separately in the root-advisory evidence. RTE-029/033/037/040/048 and
release gates are unchanged; RTE-039 completion does not release the product.

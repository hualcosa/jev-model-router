# Core implementation notes (incremental, not release acceptance)

## Configuration

`router_core/config.py` loads strict JSON global/project layers; use `../examples/routing.example.json` (validated by the loader). YAML remains conceptual, not installable. Fresh defaults are disabled and no transmission consent. Project layers may only narrow trusted global mode, enabled targets, frontier opt-in, confidence, deadline and consent. No root-switch field, arbitrary credential-source field, raw prompt log or transcript-sending option is accepted. Global config must be current-user-owned and not writable by others; both layers reject symlinks/special files with bounded nonblocking reads. Malformed settings raise sanitized ConfigError for fail-open adapter handling. The resolver returns frozen dataclasses; constructing dataclasses directly is not a validation/authorization API.

## Data and privacy

`router_core/contracts.py` defines immutable versioned task, requirement, provider and route contracts. JSON rejects duplicate/unknown fields and invalid finite scores; root decisions cannot carry selected worker routes. `safe_telemetry()` deliberately omits ALL arbitrary input strings, not only task text. Full serialization is an in-memory interchange format, not safe telemetry.

`router_core/privacy.py` accepts a single task description, not a transcript. Consent defaults to none. Synthetic consent accepts only exact trusted registered fixtures; a tool/project cannot relabel arbitrary real tasks as synthetic. Real-task consent remains ungranted in this workspace. The builder removes common credential patterns and fenced code, bounds UTF-8 payload bytes and redacts before truncation. Redaction is heuristic and cannot guarantee that arbitrary proprietary text or unknown secrets are safe to transmit. It never substitutes for consent. Outbound provider state contains only `task_summary`.

## Classifier and normalization

`router_core/classifier.py` launches the pinned optional SDK in `_jev_worker.py` using an absolute trusted file path and the same interpreter. The key is passed in memory over stdin, never argv; stdout is a small response protocol and stderr is discarded. SDK absence/version mismatch, malformed answers, process failure and timeout return explicit unavailable/failure results with no raw error text. Each request uses no transport retries. The enclosing wall deadline (default 2500ms) includes subprocess startup/import/transport; the entire worker process group is killed and reaped before returning from timeout. Installer packaging must provide the SDK in that interpreter; no implicit dependency installation happens in a hook.

The worker asks `Choice` tier/risk and three `Score` answers (complexity, reasoning, tool complexity) with a 0…2 rubric. `normalizer.py` requires all answers, validates exact shapes, divides score indices by2 and uses the minimum of the five actual confidence fields. It does not turn missing/low-confidence answers into mechanical tasks, invent confidence or interpret confidence as measured task-success probability. A successful provider result is NOT an accepted routing decision: deterministic policy must still enforce confidence, risk, pins, modes and catalog constraints.

Live core smoke: `../evidence/p1/jev-core-live-synthetic.json` used only the fixed imaginary-file task. It returned T0/low, confidence0.59 in560.53ms. This is below the provisional0.75 auto threshold and must defer in policy. It proves SDK/process/response integration, not routing quality, latency percentiles, desktop support or full E2E behavior. MockTransport tests independently verify the complete five-question SDK payload without network.

## Catalog

`router_core/catalog.py` accepts immutable schema-v1 evidence snapshots. Exact family/version policy identities are separate from executable runtime IDs; user-assumed availability does not create technical mapping evidence. Runtime, surface, host version, native tool name, allowed model/effort fields and supported effort all scope lookup. Multiple verified Agent/Task mappings are allowed; ambiguous lookup abstains rather than choosing the first. Snapshot parsing/entry counts/labels are bounded. No executable IDs, desktop support or default moving aliases are guessed. Adapters still need authoritative inventory producers.

## Verification and remaining work

Focused contracts, privacy, catalog and classifier tests pass. Unit fixtures and injected snapshots are not real catalog verification. Runtime adapters, root boundary/state/dedupe, deterministic policy, warnings/explain, packaging/install/uninstall, CLI+desktop integration, permission/conflict matrix and outcome/latency evaluation remain separate mandatory work. Existing legacy plugin is not yet migrated and its green baseline is not new-spec conformance.

# P0 feasibility evidence index

This directory contains audit evidence, not a release certificate. The full active goal is unchanged: shared router, both official runtimes, CLI and local desktop, real effective worker routing, privacy and rollback.

| Claim | Evidence | Status / limits |
|---|---|---|
| Existing fork baseline | baseline.json + baseline-1…5.txt | All five baseline checks pass; old behavior, not new-spec conformance |
| Installed runtime identities | runtime-inventory.json | CLI0.163.0 vs desktop embedded0.163.0-alpha.10.2; cannot infer parity |
| Repository/license map | repository-audit.md | RTE-001 complete; no production changes yet |
| Claude native worker model/effort | claude-cli-spike-replay.json | Actual native evidence replay passes; CLI only; no hook permissionDecision allow |
| Original minimal Claude summary | claude-cli-spike.json | Initial summary includes two runs; prefer strict single-run replay |
| SDK interface/privacy audit | jev-sdk-audit.md | Official Python SDK0.7.5 audited |
| SDK serialization contract | jev-sdk-offline.json | MockTransport only; timing is NOT provider latency |
| Live Jev readiness (historical) | jev-live-readiness.json | Initial missing-key block; resolved by live proof below |
| Live synthetic Jev | jev-live-synthetic.json | One request succeeded, jev-1.13.0, 533.48ms client elapsed; not accuracy/latency-distribution evidence |
| Codex native route | codex-cli-spike.json | User-approved native CLI model+effort proof passed; plaintext worker task unavailable at hook; desktop still pending |
| Codex hybrid composition | codex-hybrid-spike.json | Same exec proves plaintext preparation + native hook route; static fixture, no production reference controls or Jev |
| Desktop smoke (both) | pending | Required; not replaced by running a packaged CLI executable |

## Reproduction

- Existing native Claude proof can be replayed/validated without spending tokens; tests in `tests/test_claude_spike.py` also show which weak evidence is rejected.
- Explicit new native run: `python3 scripts/spikes/claude_route_smoke.py --run-synthetic --output <private-report.json>`. Consumes official Claude usage; creates only private disposable settings and no global hooks. The fixture is NOT the production router.
- SDK offline: in a private venv with `typesafe-sdk==0.7.5`, run `python scripts/spikes/jev_contract.py --output <private-report.json>`.
- Live provider: same command plus `--live-synthetic`, only after TYPESAFE_API_KEY is configured. This sends ONLY the hardcoded synthetic task; it does not authorize or accept arbitrary task text.

## Current approvals and next gate

User authorized synthetic Jev transmission and configured its private key; the one-request synthetic live smoke passed. Real-project task transmission remains unapproved. User explicitly approved the disposable Codex folder/hook and the native route test passed. RTE-004 is complete. RTE-006 is recorded in docs/09_FEASIBILITY_ADR.md: native hooks plus local preparation for encrypted Codex tasks; one live client-latency sample is available, but representative quality/latency evaluation remains pending. Neither native proof establishes desktop or live classifier behavior.

## Private credential file

The synthetic Jev probe accepts `--env-file "$HOME/.config/intelligent-agent-router/jev.env"` together with `--live-synthetic`. The file stays outside the repository, must be owned by the current user and private (0600), and contain only `TYPESAFE_API_KEY=<value>`. It is parsed as data, never sourced/evaluated by a shell; symlinks and extra assignments are rejected. The key is not printed or written to evidence. Existing environment-only use remains supported.

## Live synthetic smoke — 2026-10-19

The official SDK returned a valid response in 533.48ms total client elapsed: tier T1 with confidence0.56 and reasoning score0.44 (0…2 rubric), confidence0.32. This confirms authentication and service schema, **not correct task classification**. The task is the fixed imaginary-file example in the spike script; no project content was sent. Production must apply its configured low-confidence abstention gates. One warm/cold-unknown observation is not a percentile latency benchmark.

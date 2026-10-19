# RTE-005 — TypeSafe/Jev SDK contract audit

## Decision

Use official **Python `typesafe-sdk==0.7.5`**, Python >=3.10, MIT SDK, inside a dedicated environment. Keep the core stdlib-testable with the provider dependency optional; fail open when missing. No Node bridge or reverse-engineered HTTP API is necessary.

Primary sources inspected:
- https://github.com/typesafe-ai/typesafe-sdk-python
- https://github.com/typesafe-ai/typesafe-sdk-python/blob/main/pyproject.toml
- https://github.com/typesafe-ai/typesafe-sdk-python/blob/main/src/typesafe_sdk/_core/client/sync/client.py
- https://github.com/typesafe-ai/typesafe-sdk-python/blob/main/src/typesafe_sdk/_schemas/models.py
- https://github.com/typesafe-ai/typesafe-sdk-python/blob/main/src/typesafe_sdk/_core/retry.py
- https://help.typesafe.ai/articles/5974925716-how-is-submitted-data-used-or-retained
- https://typesafe.ai/legal/privacy-policy

The installed wheel was imported and inspected, not inferred solely from community JS references. `TypeSafeClient.system_one(state, questions, ...)` returns `.choices[name]` and `.scores[name]`. Both answer types have `confidence`; Choice has choice/probabilities, Score has score/legend/probabilities. Score is the expected rubric index and need not be an integer. SDK type validation does not replace router finite/range/contradiction checks. Never equate confidence with measured task-success probability.

## Reproducible evidence

`scripts/spikes/jev_contract.py` defaults to an official SDK MockTransport and a hardcoded synthetic task. `jev-sdk-offline.json` proves local SDK serialization/deserialization for this contract; it is NOT a live Jev result and its elapsed time is NOT provider latency. `--live-synthetic` requires TYPESAFE_API_KEY and is restricted to that same synthetic payload. `jev-live-readiness.json` currently records missing key, network_request=false. No credential was supplied or printed. User has explicitly consented to synthetic-only transmission; real project tasks remain non-consented.

The SDK default retry policy has max_retries=2 and a 30s retry budget, which violates an interactive 2.5s routing budget. Use retries=0 initially, per-operation timeout and a hard wall-clock deadline enclosing process startup/request/normalization. Cancellation and complete end-to-end timing require live validation.

## Privacy and rollout gate

No full transcript, code, paths, secrets or raw provider exception text in logs. Build bounded minimized task summaries, validate consent before key lookup/import/network, preview locally without transmitting, use standard TLS and provider authentication. A key is not consent. The provider's no-training statement is not a promise of zero retention: service/subprocessor/legal retention and tenant agreements must be reviewed before real task opt-in. SDK license does not replace service terms.

## Pending

Live synthetic service result and latency after key configuration; malformed/outage/deadline checks in the shared normalizer/client tests; scoped opt-in for actual task descriptions before production classification. Do not enable automatic routing globally from the offline result.

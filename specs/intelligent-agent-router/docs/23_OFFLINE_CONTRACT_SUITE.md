# Offline unit/property/contract baseline — RTE-034

## Status and evidence boundary

Implementation and **local** verification are present. RTE-034 remains
`in_progress`: its acceptance explicitly requires green unit/contract **CI**.
No commit/push or remote Actions run was performed for this uncommitted tree.
This does not close RTE-043 (live compatibility/version/release gates).

## Added properties

`tests/test_core_properties.py` exercises deterministic generated inputs:

- 200 seeded normalization samples: key-order invariance, no input mutation,
  exact 0..2 rubric scaling, minimum supplied confidence, and confidence lowering.
- Invalid confidence/score mutations across every answer; no invented T0 fallback.
- Both runtime profiles × three pin fields × six non-null values × three invalid
  contexts: pins bypass malformed tasks and unsupported host/schema/context,
  preserve input and do not consume the later valid assessment claim. Null and
  absent pins expose the same host guard. These are injected profiles, not new
  native host capability claims.
- Policy mode/custom/pin combinations prove zero classifier callbacks before
  cheap guards. Call counts are explicit: a callback exception swallowed by a
  fail-open implementation cannot make the test falsely pass.
- Three seeded permutations of eight runtime/project/session scopes: same call
  and event IDs cannot exchange decisions, failed claims, prepared references,
  root observations or boundary identities. Same-scope replay is idempotent;
  reset clears only its own root. These are sequential permutation properties;
  existing independent-process tests separately cover concurrent claims.
- Native-format unsupported versions, provider failures and multimodal/opaque
  inputs leave argument objects/content untouched. Forged `TaskCreated` root
  metadata cannot attest root identity or cause classification.

No property is evidence of task quality, effective runtime model/effort,
principal plugin trust, desktop support or absence of all bugs. The existing
golden corpus, provider failure fixtures and independent-process tests remain.

## Commands and CI

```sh
# Dependency-free cell: two SDK contracts may skip when SDK is absent.
python3 scripts/run_offline_tests.py

# SDK-required cell; dependency installation needs package-index network access.
python3 -m pip install 'typesafe-sdk==0.7.5'
python3 scripts/run_offline_tests.py --require-sdk
```

The SDK-required runner fails before discovery on absent/wrong SDK version or
unimportable SDK/transport; it fails any skipped test or unsuccessful suite.
SDK calls in these contracts use `httpx2.MockTransport`. No provider key or
native runtime is needed. SDK version is pinned; transitive dependencies are
resolved by pip, **not** a fully locked environment.

`.github/workflows/test.yml` retains legacy integration/eval/docs/variant gates
and adds a separate Python 3.11 SDK-required job, empty provider-key variables,
15-minute timeout, read-only contents permission and no persisted checkout
credentials. This follows GitHub's [Python setup inputs](https://github.com/actions/setup-python/blob/main/docs/advanced-usage.md)
and [token permission guidance](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token).
No live provider tests are added to pull requests. This is not an OS-level
network sandbox and does not claim to enforce network isolation for arbitrary
future test code.

## Verified locally — 2026-10-19

- macOS arm64, Python **3.11.16**: **673 tests**, two optional SDK skips.
- Fresh isolated Python 3.11 venv, SDK **0.7.5**: **673 tests**, zero skips.
- Missing-SDK required mode: exit **2**, stable sanitized diagnostic.
- Legacy `tests/test-hook.sh`: **48 passed / 0 failed**.
- Legacy `tests/eval/run_eval.py`: **70/70** classification fixtures and gates
  passed. This is not new-router task-outcome success or measured quota savings.
- Docs and agent-variant parity checks passed.

Machine-readable local record: `../evidence/p1/offline-contract-suite-local.json`.
The authoritative remote-CI gate is still pending.

## Requirements not silently relaxed

TC-034 still requests native Codex `message` and text-only `items` handling.
Observed opaque `message` payloads require the approved local prepared-reference
flow; generic text-only `items` support is **not established**. Tests assert safe
no-op on unsupported shapes, not fulfillment of the complete TC-034 requirement.
TC-004 `TaskCreated` hints do not establish trusted native root provenance.
Actual compatibility and desktop requirements remain open in their tasks.

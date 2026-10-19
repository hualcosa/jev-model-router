# Security and approval boundaries — RTE-038

## Scope and result

The shared-core threat model, adversarial fixtures and scoped native regression
are verified. Two medium defects were reproduced, fixed and independently
rechecked. This is **not** a claim that all native approval modes, competing
hooks or desktop surfaces are supported; those remain release gates in
RTE-029/033/047/048. The legacy Claude plugin has not yet been replaced
(RTE-024/027), so this report does not certify its upstream autoswitch behavior.

Assets: provider credentials, task/code confidentiality, explicit user controls,
root model/effort, native approval/sandbox authority, prepared capabilities,
private telemetry and local package integrity.

Trust boundary: global user-owned configuration and reviewed runtime capability
evidence grant authority; project settings may narrow but not broaden it. Model
task text, native input arguments, provider answers and project configuration
are not executable instructions or sources of permission authority. A process
already running as the same OS user is outside the private-state protection
boundary; local filesystem mode checks are not a sandbox against that process.

## Threat/control/evidence matrix

| Threat | Control and evidence | Residual limit |
|---|---|---|
| Shell metacharacters or native placeholder injection | `packaging.py` quotes every explicit argument, rejects `${` in path bindings and uses double-quoted unbraced `$PLUGIN_ROOT`; packaging sentinel tests execute malicious-looking path bytes without substitution | Native principal trust/install still separately required; no claim about arbitrary external hook commands |
| Prompt exfiltration without opt-in | Exact immutable synthetic fixture registry; global consent; project cannot grant consent; lazy credential load after gates; privacy/config/MCP tests | Redaction is best effort, **not** authorization to send arbitrary private code |
| Partial detected-secret redaction | Fixed escaped quote/backslash pairs, multiline and unterminated quoted values; regression failed on old code and passes after fix | Unknown secret formats or arbitrary confidential prose can remain; real-task transmission remains off without separate opt-in |
| Project config injection | Strict fields/types, duplicate/depth/size checks, monotonic project restrictions, global ownership/mode checks; config tests | Owner-level malicious code or replacement of trusted binaries is outside this boundary |
| Explicit generic profile control bypass | Actual validated native `agent_type` checked before prepared-reference consumption or cached replay; regression rejected `default` when disabled and preserved reference for permitted omitted-type retry | Preparation is attestation, not cryptographic plaintext-to-opaque-task equality |
| Permission escalation on unrelated tools/lifecycle | New `test_security_boundaries.py`: unrelated shell/edit/read/MCP lookalikes return no output; lifecycle output cannot contain permission/routing overrides; injected argument permission fields rejected with zero classification | Fixture proof is about adapter output, not a complete native sandbox penetration test |
| Codex `permissionDecision=allow` | Emitted only for validated target spawn, current policy/catalog/snapshot and reviewed conflict evidence in an exact measured mode; unmeasured modes reject before consuming capability | Only measured CLI `bypassPermissions`/read-only/never context has native evidence. On-request and desktop are not proven |
| Permission/sandbox changes on routed child | Native 0.163.0 regression: root Sol6.1/Low, child Luna6/Medium, both approval `never`, sandbox `read-only`; original non-route fields preserved | Host-reported synthetic context is test-only evidence, not parsed by production; no claim that a forbidden write was attempted |
| Other-hook conflict or stale authority | Public inventory checks trust, enabled state, duplicate/async/matcher overlap, binary/code/scope/expiry bindings; ambiguous state disables auto; profile tests | Independent inventory subprocess may not reflect originating-session invocation-only overrides. Not established as a defect; do not advertise arbitrary override/coexistence support before native compatibility tests |
| State/telemetry leakage or race | Hashes/strict allowlists/private modes, bounded records/locks, at-most-once retained claims; independent-process tests and retained telemetry/explain tests | Retention is bounded best effort, not durable exactly-once execution or a full history archive |

## Fixed findings

1. **Detected secret suffix leak** (`privacy.py`). A valid JSON password with an
   escaped quote was only partly replaced. The new quote-aware pattern consumes
   escape pairs atomically and does not fall back to an unquoted partial match.
   Regressions cover JSON escapes, single quotes, multiline input, missing
   closing quote and a trailing backslash. The test uses invented markers only.
2. **Prepared explicit-generic restriction bypass** (`native.py`). Preparation
   has no eventual native agent type; the later Codex spawn could bypass
   `allow_verified_generic_type=false`. The adapter now rechecks the actual
   validated type before touching a reference or cached claim. Implicit-type
   routing remains allowed, as intended by that specific control.

## Verification — 2026-10-19

- Focused privacy: **12 tests**; native adapter: **14 tests**; additional
  permission-boundary matrix: **4 tests**.
- Full Python 3.11.16 suite: **680 tests**; default environment two optional SDK
  skips, isolated SDK 0.7.5 environment zero skips.
- Real official Codex **0.163.0 CLI** run in the already reviewed disposable
  folder: one prepared task, one injected classification callback, one native
  child, correct effective model/effort, root unchanged, read-only/never inherited.
  **Zero Jev calls**. Original temporary scripts restored to mode 0644; native
  hook definitions/trust were not changed or bypassed.
- Two bounded read-only security reviews requested Sol6.1/High. Actual worker
  configuration was not independently observable, so no assertion that the
  override succeeded. Both concrete fixes were independently repro-rechecked.
- Gitleaks **8.30.1**, local directory scans with full redaction: `router_core/`,
  `scripts/`, and spec package **zero findings**. `tests/` had **five findings**:
  two source fixture matches (invented AWS token and literal dummy private-key
  block) plus three bytecode copies of dummy key text. These are intentional
  fake fixtures; they were not suppressed or represented as a clean test-tree
  scan. No raw match/secret values are included in the report.

### Tooling limits

The local security skill file was unreadable (`Operation not permitted`, also
after escalated read). Installed Semgrep **1.174.0** failed before scanning
because its required tree-sitter **0.26** dylib was missing. No Homebrew/global
library changes were made to repair it. Trivy and Checkov were not run in this
bounded Python authority review. Therefore this is **not** a completed full
four-scanner security-skill run or a clean SAST/SCA certification.

Records: `../evidence/p1/security-boundaries-local.json` and
`../evidence/p1/codex-security-regression-native.json`. No commit, push, principal
plugin installation, global activation or real-task provider opt-in occurred.

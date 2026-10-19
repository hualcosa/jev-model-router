# 06 — Verification, Evaluation and Rollout Plan

## 1. Test philosophy

Separate four kinds of evidence:

1. **Unit tests:** deterministic pure contracts/policy/state logic.
2. **Hook contract tests:** valid host JSON input and outputs, including unsupported tool schema.
3. **Live smoke tests:** actual official `claude` and `codex` runtimes; verify effective worker model/effort rather than returned JSON alone.
4. **Task outcome eval:** representative engineering tasks, measuring accepted outcomes and total work rather than only a classifier recommendation.

**A mock hook that emits `updatedInput` is not proof the host executed that model.** Do not ship without live verification.

## 2. Minimum unit/contract fixture matrix

| Test ID | Input | Expected |
|---|---|---|
| TC-001 | Same task continued across 4 root prompts | No additional Jev requests for continuation |
| TC-002 | New root task marker | Exactly one classification and at most one warning |
| TC-003 | Unknown boundary | No Jev call by default; manual preflight offered |
| TC-004 | `TaskCreated` new item in Claude | Strong boundary hint, no duplicate task identity |
| TC-005 | Root on Sonnet; strong recommendation Opus | Advisory only, root unchanged |
| TC-006 | Root on Sol Medium; recommend Sol High | Effort-only advisory, root unchanged |
| TC-007 | Root already stronger than recommendation | No downgrade warning |
| TC-008 | Insufficient confidence | Abstain/ignore according to configured minimum; no arbitrary downgrade |
| TC-009 | Unknown actual root effort | Do not fabricate effort difference |
| TC-010 | Explicit worker `model` | No Jev call, no rewrite |
| TC-011 | Explicit worker `reasoning_effort` only | Full spawn bypass (v1 conservative policy) |
| TC-012 | Custom or unknown agent type/profile | Full spawn bypass before classification |
| TC-013 | Unpinned T0 child spawn | Valid low-tier model selected from verified catalog |
| TC-014 | Unpinned T2 child spawn | Valid capability-floor-respecting strong route |
| TC-015 | Unsupported Claude agent effort | No unsupported argument added; logged advisory-only |
| TC-016 | Unsupported Codex effort | Native spawn inherited, not error |
| TC-017 | Unsupported model/version | Defer, no rewrite |
| TC-018 | Provider timeout | Native tool call unchanged; reason logged |
| TC-019 | Malformed Jev response | Deferred with invalid_schema |
| TC-020 | Missing key or third-party consent | No outbound request; native execution unchanged |
| TC-021 | Explicit frontier opt-out | No frontier automatic route even if Jev recommends it |
| TC-022 | Security-sensitive, short change | Capability/risk floor prevents trivial-model downgrade |
| TC-023 | `PostToolUse` inside running child | Zero new classifications |
| TC-024 | Duplicate hook invocation same tool call | Idempotent decision, no multiple TypeSafe calls |
| TC-025 | Three concurrent independent child spawns | Correct per-child decisions, no state crossing |
| TC-026 | Resume/compaction with stale state | Registry refreshed; warnings not spammed |
| TC-027 | Model changed manually by user | Router does not block/revert; next state correct |
| TC-028 | Tool not Agent/spawn_agent | Zero Jev requests and no arguments touched |
| TC-029 | Native sandbox/permission fields | Original fields preserved exactly |
| TC-030 | Secret in task description | Secrets removed/masked or call refused according to policy |
| TC-031 | File-state permissions | New state file private; no raw prompt by default |
| TC-032 | Shadow mode child | Recommendation logged; tool args unchanged |
| TC-033 | Router disabled | All hooks no-op |
| TC-034 | Codex `message` and text-only `items` | Both handled, task text intact |
| TC-035 | Non-text multimodal child input | Skip with reason; no unsafe stringification |
| TC-036 | Two hooks rewrite same spawn | Detect/document conflict and avoid claims of determinism |
| TC-037 | Explain command after decision | No new Jev call; stored provenance accurate |
| TC-038 | Invalid config | Explicit safe diagnostic; no silent unsafe defaults |
| TC-039 | Host says `model` not yet verified | Telemetry labels `actual_unverified` |
| TC-040 | Provider temporary outage | Bounded deadline, no runaway retries |
| TC-041 | Target Terra 6, verified runtime offers only Terra 5.6 | No substitution to 5.6; target unavailable recorded; native inputs unchanged if no eligible route remains |
| TC-042 | Generic family alias with unknown/resolved different version | Candidate excluded; no guessed runtime ID or silent version upgrade |
| TC-043 | Target account availability assumed by user; exact IDs/versions technically verified | No entitlement-discovery prerequisite; availability provenance remains user_assumption; frontier/effort guards still apply |
| TC-044 | Verified generic default type with no model/effort pin | Eligible; router chooses supported model/effort |
| TC-045 | Root populated a model/effort pin without user provenance | Bypass unchanged; never guess provenance or erase the pin |
| TC-046 | Generic delegation emitted by product guidance | Task supplied without preselected model/effort; explicit human choices remain pinned |

### Current offline evidence is not native support

See [RTE-034 offline baseline](23_OFFLINE_CONTRACT_SUITE.md). In particular,
TC-034 remains a requirement, **not a completed capability**: observed opaque
Codex `message` requires local approved preparation; native text-only `items`
handling is unverified/unsupported by the current profile. Safe unchanged
fallback tests do not fulfill the original dual-shape support requirement.
Likewise TC-004 `TaskCreated` hints are not trusted root provenance; forged or
nested task metadata must not attest a new root identity.

## 3. Live compatibility matrix

For **each** installed runtime/version/surface, create an auditable run record with:

- root model and effort before/after;
- reported hook version and trust state;
- original tool call JSON (redacted), rewritten JSON (redacted), host's actual worker model and effort evidence;
- task ID/tool call ID and routing log entry;
- permission/sandbox behavior;
- resolved capability (`supported`, `unsupported`, `unverified`).

Minimum matrix:

| Scenario | Claude CLI | Claude desktop (Code/local) | Codex CLI | Codex desktop (local) |
|---|---|---|---|---|
| Root warning only | required | required | required | required |
| Automatic unpinned worker model | required | required | required | required |
| Automatic unpinned worker effort | prove support or disclose gap | prove support or disclose gap | required if supported | required if supported |
| Explicit model/effort pin | required | required | required | required |
| API unavailable/timeouts | required | required | required | required |
| Multiple parallel workers | required | required | required | required |
| Resume/compact | required | required | required | required |
| Disable/uninstall | required | required | required | required |

Desktop is a mandatory acceptance surface. Same harness is a reuse expectation, not proof of hook loading/trust, credentials, warning visibility, permissions or effective child execution. IDE extensions, ordinary chat, cloud and remote sessions are not implicitly covered.

Codex **hosted tools** may bypass local function-tool hooks: explicitly label such execution paths outside the coverage claim.

## 4. Routing corpus and experimental comparison

Create **at least 60 labeled tasks** plus **30 multi-turn sequences** for boundary detection. Include:

- code search/extraction; simple edits and dependency bumps;
- familiar scoped feature work; tests, frontend, API integrations;
- unknown-cause failure analysis; cross-module concurrency; migrations; auth/security;
- long prompts that are easy; short prompts that are hard;
- ambiguous continuations, “one more thing” scope changes, interruptions and resumes;
- explicit model pins, no pins, custom agent types, and missing model catalog.

Compare variants using the **same task/harness/version** and repeat stochastic outcomes:

A. Original repo heuristics (baseline).

B. Jev task requirements + benchmark-informed policy.

C. Root model's own explicit subagent selection (where the harness supports it).

D. No router/native inheritance (operational baseline).

Record at minimum: (i) accepted-code/test quality, (ii) human correction/rework, (iii) retries/escalation, (iv) end-to-end wall time, (v) model and effort chosen, (vi) Jev call count/latency, (vii) generated/output and cache metrics if exposed, (viii) estimated API cost only when measured via a real API rate card. On subscription plans, report consumption proxies instead of pretending to know billing equivalence.

## 5. Suggested engineering quality gates (initial, amend after pilot)

These are **proposed release gates**, not prior benchmark results:

- **0 unauthorized root switches** across unit + live tests.
- **0 unsupported field rewrites** in validated hook schemas.
- **0 outbound Jev calls** in obvious continuation and internal-tool fixtures.
- **At most one logical classification per new unpinned worker spawn**; retries capped.
- **100% intentional pins respected** in fixture suite.
- **100% Jev fault scenarios** fail open without broadening execution permissions.
- **100% test fixtures** preserve original task payload and nonrouting permissions.
- **Zero raw secrets** in telemetry/artifacts.
- **Root advisory rate:** duplicate warnings per task = 0 in labeled sequences.
- **Router call overhead:** instrument p50/p95; propose p95 <2500ms for warmed classification; if not met, tune or use a lower default deadline. No absolute SLA until TypeSafe measured.
- **Boundary false positive rate:** aim <5% on labeled continuations; report false negatives (missed new tasks) separately. No arbitrary inference that accuracy of a classifier is the same as task-boundary accuracy.
- **Worker quality:** no material degradation in accepted-task rate vs native or heuristic baseline on chosen corpus; report sample size and uncertainty.

## 6. Shadow -> pilot -> rollout

1. **Unit + contract** with synthetic and recorded safely redacted JSON fixtures.
2. **Shadow** in both official CLIs: evaluate recommendations but do not mutate tool arguments.
3. **Auto workers in Claude only** for a small subset after smoke proof; Codex remains shadow.
4. **Auto workers in Codex** after its own effort/model smoke proof; do not borrow Claude evidence.
5. **Broaden** task categories/versions after task-outcome eval shows no regression.
6. Keep `disabled` flag, uninstall instructions, compatibility matrix, and rollback command in release README.

## 7. Investigation checklist for Claude vs Codex deviations

- Does current host supply `tool_use_id` and stable session ID to every hook? If not, choose a documented alternative or conservative idempotency bound.
- Does the hook output have visible user-facing warning semantics, or only model-readable context?
- Can worker effort be set directly on the relevant tool, or only through agent profiles?
- Can actual model/effort be observed, rather than merely requested?
- Do multiple hooks applying `updatedInput` have stable merge priority? If not, define a conflict policy.
- Does `permissionDecision:"allow"` bypass approvals for child spawn? Test this with explicit sandbox restrictions.
- How do user, project, managed, plugin and cloud session hooks interact?
- Does the TypeSafe API return a confidence score with the same meaning across request forms?
- Are quoted historical Artificial Analysis cost/task numbers comparable in methodology/version?

## 8. Release report template

```text
Build ID / commit SHA:
Date / platform:
Claude version + surface:
Codex version + surface:
TypeSafe SDK/version:
Policy/catalog version:

Capability matrix (supported / unsupported / unknown):
- Root model observed:
- Root effort observed:
- Root advisory:
- Worker model mutation:
- Worker effort mutation:
- Effective model verified:
- Effective effort verified:
- Normal permissions unaffected:

Tests passed / failed:
Shadow Jev calls / unique eligible child tasks:
P50/P95 classification latency:
Boundary precision and recall:
Worker task success / retries vs baseline:
Security review outcome:
Known unsupported paths:
Rollback procedure verified:
Release decision:
```

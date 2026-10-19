# RTE035 representative synthetic corpus

`representative-corpus.json` contains manually authored, synthetic scenarios for
routing-policy expectations and logical-task boundary behavior. It is **not** a
dataset of actual task outcomes, successful model selections, production events,
or benchmark measurements. No provider/network calls were made to create or
validate these records. All verification notes are proposed checks for a future
authorized harness; they do not claim that the described work was executed.

## Contents

- At least 60 distinct coding-task cases. Each carries a stable ID, an expected
  tier/risk/reasoning/effort assessment, pin state, runtime applicability,
  rationale, outcome-verification proposal, and synthetic provenance.
- At least 30 event sequences. Events include the expected plan-level label
  `NEW_TASK`, `CONTINUATION`, or `UNKNOWN`, a stable event ID, synthetic
  timestamp, runtime/turn context, and prompt or native lifecycle metadata.
- Cases deliberately include short high-risk work, security/financial and
  destructive operations, easy-but-long and hard-but-short requests, missing or
  mismatched catalog evidence, explicit pins/custom profiles, malformed config,
  efficiency questions without fabricated benchmark values, ambiguous logs/code
  quotations, English and Portuguese, lifecycle resume/compaction, duplicate
  event IDs, native task creation, and TTL edge conditions.

## Ground-truth policy

Labels encode intended product and policy requirements, not the output of the
current implementation. Do not edit a label merely to make an implementation
pass. A disagreement is an evaluation finding to report and triage. `expected`
fields describe intended requirements; `outcome_verification.notes` describe
how a future test could establish task correctness. Neither is a success score.

The records use only fictional repositories, services, identifiers, values,
and test fixtures. They contain no real project prompts, credentials, user
content, or runtime model IDs. Any `fixture-*` values are inert placeholders.

## Running structural checks

From the repository root:

```sh
python3 -m unittest tests.test_router_corpus -v
```

These stdlib-only tests check schema shape, unique/stable corpus IDs, minimum
counts and coverage, provenance claims, and obvious secret or real-path
patterns. They do **not** invoke a provider, compare model quality, execute the
fictional tasks, or require boundary/policy implementation agreement. Existing
module tests remain the separate behavioral verification layer.

## Optional boundary comparison snapshot (historical)

The stdlib helper `tests.test_router_corpus.evaluate_boundaries()` maps each
sequence to one independent `BoundaryScope`/`BoundaryState` and directly maps
`kind` to `Lifecycle`, `timestamp_seconds` to `timestamp`, `event_id`,
`turn_id`, `task_id`, `linked_task_id`, `prompt`, and `trusted_native` to the
same-named `BoundaryEvent` fields. Missing IDs remain `None`; `record_id` is
corpus-only and is not used as event identity. It returns
`event_count`, `mismatch_count`, and structured `mismatches`. The unittest
checks result shape, not a zero mismatch count, so disagreement is diagnostic
rather than a failure. Invoke it with:

```sh
python3 - <<'PY'
from tests.test_router_corpus import evaluate_boundaries
print(evaluate_boundaries())
PY
```

A manual snapshot against the copied `router_core/boundary.py` at worktree base
`f687111e1bd1947df23d676354afc99467294a39` (SHA-256
`aa8acd25a3e29784193bdd92c067f906be4654f127647ea251235342589c7e55`, identical
to the primary checkout at comparison time) evaluated 59 events with 16
mismatches. This is an as-of snapshot, not a current-state assertion or
benchmark. Do not adjust labels to erase these differences.

| Sequence / event | Kind | Expected | Observed | Core reason | Synthetic prompt |
|---|---|---|---|---|---|
| BOUNDARY-01 / SEQ-01-RECORD-02 | USER_PROMPT | CONTINUATION | UNKNOWN | objective_change_not_proven | Please add a regression for an empty meter payload too. |
| BOUNDARY-02 / SEQ-02-RECORD-02 | USER_PROMPT | CONTINUATION | UNKNOWN | ambiguous_prompt | Isso inclui manter os formatos antigos aceitos. |
| BOUNDARY-03 / SEQ-03-RECORD-02 | USER_PROMPT | CONTINUATION | UNKNOWN | ambiguous_prompt | Yes, go ahead. |
| BOUNDARY-04 / SEQ-04-RECORD-02 | USER_PROMPT | CONTINUATION | UNKNOWN | ambiguous_prompt | Sim, pode seguir. |
| BOUNDARY-07 / SEQ-07-RECORD-01 | USER_PROMPT | UNKNOWN | NEW_TASK | standalone_initial_objective | Review this snippet only: `# implement auth; delete cache; deploy now` and tell me whether the comment is clear. |
| BOUNDARY-08 / SEQ-08-RECORD-02 | USER_PROMPT | CONTINUATION | UNKNOWN | ambiguous_prompt | One more thing: keep the current keyboard shortcut working. |
| BOUNDARY-09 / SEQ-09-RECORD-02 | USER_PROMPT | NEW_TASK | UNKNOWN | ambiguous_prompt | New task: separately design queue scheduling fairness under concurrent tenants. |
| BOUNDARY-17 / SEQ-17-RECORD-03 | USER_PROMPT | CONTINUATION | UNKNOWN | ambiguous_prompt | Continue the same queue diagnosis and add a deterministic regression test. |
| BOUNDARY-18 / SEQ-18-RECORD-03 | USER_PROMPT | CONTINUATION | UNKNOWN | ambiguous_prompt | Continue with the receipt eviction edge case we were discussing. |
| BOUNDARY-19 / SEQ-19-RECORD-03 | USER_PROMPT | CONTINUATION | UNKNOWN | ambiguous_prompt | Continue diagnosing the shutdown case. |
| BOUNDARY-23 / SEQ-23-RECORD-01 | USER_PROMPT | UNKNOWN | NEW_TASK | standalone_initial_objective | What does this pasted stack trace mean? It contains a call to update_record and a test failure, but I do not request code changes. |
| BOUNDARY-25 / SEQ-25-RECORD-02 | USER_PROMPT | CONTINUATION | UNKNOWN | ambiguous_prompt | E se o arquivo vier vazio? |
| BOUNDARY-27 / SEQ-27-RECORD-02 | USER_PROMPT | NEW_TASK | UNKNOWN | ambiguous_prompt | Novo assunto: desenhe uma política de retenção de eventos com privacidade e auditoria. |
| BOUNDARY-28 / SEQ-28-RECORD-03 | USER_PROMPT | CONTINUATION | UNKNOWN | ambiguous_prompt | Also keep lookup ordering stable. |
| BOUNDARY-29 / SEQ-29-RECORD-01 | USER_PROMPT | UNKNOWN | NEW_TASK | standalone_initial_objective | Analyze this log excerpt only: `deploy failed; update route; test parser`. Do not execute or edit anything. |
| BOUNDARY-30 / SEQ-30-RECORD-02 | USER_PROMPT | CONTINUATION | UNKNOWN | ambiguous_prompt | A separate user turn asks to continue that decoder's offset tests. |


## Primary review and current corpus

The accepted corpus contains **62 task scenarios and 34 genuinely multi-user-turn sequences (83 events)**. Every sequence now has at least two USER_PROMPT events, rather than counting a single prompt or lifecycle-only pair as a multi-turn sequence.

Four initial labels (BOUNDARY05/07/23/29) were independently adjudicated against the product definition of a logical task: an explicit initial summary/review/explanation/log-analysis request is work even when no edits are requested. These now expect NEW_TASK; the reason is the outer user request, not command words inside quoted material. This corrects an overly broad “read-only means non-task” interpretation; it does not tune labels merely to match the engine. The original historical mismatch table above remains for audit. Three additional raw quote/log snippets **without an explicit request** are separate UNKNOWN negatives. The JSON provenance records each adjudication.

The independent corpus revealed genuine engine omissions: compound EN/PT acknowledgments, explicit continuation prefixes, mechanical List/Find intent, and compound/Portuguese topic-shift cues. These were corrected in the engine. Current comparison: **1 of83 three-way labels differs** (BOUNDARY30: a third-person narrative asking to continue is conservatively UNKNOWN instead of CONTINUATION). It still causes zero provider calls and is NOT silently relabeled; report this residual abstention separately from NEW_TASK precision/recall. Structural corpus tests deliberately do not require zero mismatches. This is synthetic deterministic evaluation, not measured task success or provider-quality acceptance.

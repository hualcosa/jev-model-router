# Privacy-safe telemetry — RTE-036

## Implemented and verified

The shared native adapter writes schema-1, single-line JSON records to the private
state directory when enabled and `observability.log_decisions` is true. Disabled
mode and logging-off perform **no telemetry I/O**. No global installation or
activation was performed for this work.

- Assessment: normalized requirements, confidence, disposition/reason,
  selected/recommended model and effort, policy hash, policy/catalog snapshot
  hashes, actual callback count (0/1), provider status, assessment elapsed ms.
- Activity: boundary classification/reason; native spawn recognition, pin/custom/
  permission fallbacks, durable computed/cached/inflight/error result, rewrite
  emission; root warning emission; prepared-task result/issuance.
- Observation: requested post-tool arguments **separate** from host-reported
  actual model/effort. Emitted hook output is not proof the host applied it.
- Source, runtime, measured host version, mode, timestamp and random row ID.
  Scope/session, task, tool and agent identities are SHA-256 scoped hashes, not
  plaintext IDs. `requirements.provider_raw_tier`, provider names/prose, prompts,
  tool responses, custom agent names, transcripts, paths and credentials are not
  persisted. Unsupported labels become null; unknown reasons become a fixed
  `unclassified_reason`, not arbitrary user/provider text.

### Host truth, not inferred execution

Only measured CLI versions are consumed by observation producers:

| Event | Codex 0.163.0 | Claude Code 2.1.303 |
| --- | --- | --- |
| SessionStart | model reported when present; effort unknown | model reported when present; effort unknown |
| UserPromptSubmit | model reported when present; effort unknown | no observation producer |
| PostToolUse (native spawn only) | argument model/effort, actual unknown | argument model/effort, actual unknown |
| SubagentStart | child model reported; effort unknown | model/effort unknown |
| SubagentStop | child model reported; effort unknown | child effort.level reported if present; model unknown |
| PostModelSwitch | unsupported | to_model reported; effort unknown |

Actual execution is `reported_by_host` only for the documented available field,
otherwise `unverified`. This implementation never marks an observation `verified`
and does not manufacture mismatches. There is **no documented reliable join**
from parent `tool_use_id` to lifecycle `agent_id`; records keep separate hashes
and `correlation: unverified`. Concurrent children are never paired by order.
Unknown model labels remain unknown, not inherited or guessed.

The Codex builder now registers eight events: SessionStart, UserPromptSubmit,
PreToolUse, PostToolUse, SubagentStart, SubagentStop, PostCompact, SessionEnd.
PostToolUse uses the same spawn-only matcher as PreToolUse. Adding hooks changes
the content-derived package version and requires fresh native review; no trust
record is copied or patched. Claude packaging is a separate pending task.

## Storage, retention and failure behavior

`TelemetryLog` uses the existing descriptor-anchored private state root (0700),
0600 single-link regular files, no-follow opens and existing state.lock. It never
holds the lock across a provider callback. Files are atomically published using
bounded temporary files/fsync/replace; there is no crash-torn append operation.
All existing current/archive JSONL schemas and private permissions are checked
before writing. Unsafe symlinks, hard links, FIFOs, public files, oversized or
invalid/torn records are rejected, not repaired or overwritten.

Default retention is **size-based, not time-based**: three files of at most
256 KiB each (`telemetry.jsonl`, `telemetry.1.jsonl`, `telemetry.2.jsonl`), plus one
bounded atomic temporary file. State TTL does not imply telemetry TTL. Rotation
can duplicate old records if interrupted; the reader deduplicates row IDs.
Logging is best-effort, **not exactly-once audit delivery**; bounded retention or
errors can omit history. Never infer provider totals from an incomplete window.

The reader opens an existing root/lock under a bounded shared lock. It does not
create directories/locks, clean temporaries, read credentials, call providers or
change routing state. It validates the record schema again. `explain` now uses this reader via RTE-042; see `22_OFFLINE_EXPLAIN.md`
for the implemented CLI and its separate verification.

Audit errors are swallowed by the adapter, not exposed as exception prose and
not used to change routing/native output, retry classification or block a user.
Existing at-most-once classifier claims and boundary/root atomicity remain in
force. Assessment elapsed time excludes snapshot persistence and log publication;
end-to-end UX/log overhead remains RTE-039, not a performance claim here.

## Evidence and remaining release gates

- `tests/test_core_telemetry.py`: 26 tests, including separate-process first-use
  concurrency, read/write locking, bounded rotation, duplicate crash rows,
  interrupted publication, unsafe files, strict schema/huge integers, privacy,
  cache/no-recall, provider exceptions, shadow no mutation, disabled/no-log I/O,
  and child observation/root isolation.
- Full default suite: 620 pass with two optional SDK skips. Pinned SDK 0.7.5
  interpreter: all 620 pass, no skips. Source review: no medium/high findings.
- `../evidence/p1/codex-package-telemetry-native.json`: actual Codex 0.163.0
  isolated native install/list/doctor/disable/uninstall/marketplace removal;
  all eight hooks discovered, own spawn command recognized, all untrusted,
  zero inference/Jev calls, principal config hashes unchanged.
- Historical first smoke failure is retained separately: the old harness still
  expected five hooks. Corrected to validate the exact eight-event set; the
  failed isolated registration/cache was removed via native CLI commands.

RTE-036 covers core shadow logging and available host observation contracts.
This is **not** proof of trusted packaged hook execution, live Claude observation
integration, desktop operation, task-quality gains or subscription savings.
Those remain RTE-028/029/032/033/037/039/048 as applicable. No real project data
was sent to Jev. Principal temporary installation/trust approval is still pending.

Official contracts used for the read-only audit:
- https://developers.openai.com/codex/hooks/
- https://code.claude.com/docs/en/hooks

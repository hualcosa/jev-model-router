# Persistent state and native adapters — current checkpoint

## State

`router_core/state.py` uses private 0700 directories and single-link 0600 regular files, descriptor-anchored traversal, no-follow/nonblocking opens, bounded fcntl locks and atomic fsync/replace. Scope and native IDs are hashed. Record counts, bytes, TTL and lock waits are bounded; corrupt/unsafe state fails open with reason codes, never raw errors. A durable claim is written **before** a callback, outside whose execution no lock is held. Concurrent hooks reuse the decision or abstain while it is in flight. Failures/crashes do not reclassify within the retention window. This is at-most-once execution, not guaranteed delivery/success. TTL expires retained decisions, so this is not an unlimited replay ledger.

Prepared references are random native-valid names, scoped to runtime/project/session, expiring and atomically single-use. Only typed routing decisions are stored, not prepared plaintext. References are hashed on disk. Preparation retries with the same stable task_id do not classify again or mint another reference; crash/lost response safely sacrifices routing. Binding remains orchestrator-attested, NOT cryptographic equality with the opaque native task message. Root observations and warning fingerprints are private/bounded; lifecycle reset clears observations while retaining warning dedupe.

26 state tests include independent-process same-key/different-scope stress, crash retention, parallel single-use consumption, corruption/permissions/symlink/hardlink/FIFO/capacity/clock checks. The worker reported one earlier conservative ERROR without its code captured, but no duplicate callback; subsequent bounded tests and primary tests passed. Fail-open uncertainty is disclosed rather than called guaranteed success.

## Native pipeline

`native.py`, `preparation.py`, `hook.py`, `mcp.py`, and absolute-path launchers `scripts/router_hook.py` / `router_mcp.py` connect typed profiles, consent/minimization, deterministic policy and persistent state. Unknown versions/surfaces/schema/conflicts/permission modes abstain. Hooks never read private transcripts, alter model settings, erase pins or rewrite non-agent tools. Cached/prepared routes are revalidated against current catalog, target versions, effort, confidence and frontier restrictions. Claude emits only updatedInput; Codex requires allow and remains gated on explicitly tested permission modes plus conflict checks. Bootstrap CLI profiles cover only P0-verified Haiku/Medium and Luna/Medium primitives; they default to **no automatic mutation** pending installation diagnostics. They are not the full required model inventory and never extrapolate desktop support.

The MCP facade exposes only prepare_task, not files/shell/execution. It has ordinary plaintext input, fixed registered project, a SessionStart-supplied native session ID and stable logical task_id. Transmission still requires configured consent; a project cannot authorize real tasks. Its annotations honestly indicate possible external interaction and local state effects. It never returns model/effort for the root to select. Synthetic fixture allowlists are injected only by trusted application/test code, never tool arguments/project config.

Claude uses prompt_id, optional SessionStart.model, PostModelSwitch.to_model and effort.level observations. Missing model stays unknown; model/effort are never inferred from settings. Root submission advice uses nonblocking systemMessage/context and atomic warning reservation. These output shapes have unit coverage; actual visible warning/desktop UX still needs host smoke.

Sources checked for native contracts: [Claude hooks reference](https://code.claude.com/docs/en/hooks), [official Codex hooks](https://learn.chatgpt.com/docs/hooks). Codex documents allow paired with updatedInput; that alone is not proof of permission preservation. Claude documents the optional startup model and supported observation fields; it does not guarantee model availability at every hook.

## Verified native composition

`evidence/p1/claude-core-native.json` is a **new real official Claude2.1.303 run**, not a replay of the static P0 fixture. Shared core/policy/private state/native adapter performed exactly one injected deterministic synthetic classification, selected Haiku5.5/Medium, preserved all nonrouting arguments, and actual native result.modelUsage/lifecycle confirmed child Haiku/Medium versus root Sonnet5.5/High. No permissionDecision allow, no Jev call, no global install. The classifier was deliberately injected; this is not a claim of full live-Jev E2E, full catalog, conflict matrix or desktop completion.

## Corpus

The accepted corpus has62 task cases and34 genuinely multi-user-turn sequences/83 events. Four initial read-only-request labels were independently corrected against the product definition, with provenance; original historical mismatch report remains. Current comparison leaves one conservative UNKNOWN-versus-CONTINUATION discrepancy with zero extra provider calls. Corpus structural green is not a zero-mismatch or task-success gate. See CORPUS.md and evidence/p1/boundary-corpus-eval.json.

## Remaining gates

Codex new-core native composition, real-Jev-to-native selected-route integration, broader exact inventory, actual visible root warnings, plugin packaging/install/rollback, both desktop sessions, full permission/conflict matrix and representative outcome/latency evaluation remain pending. Legacy upstream hooks are not yet migrated. No global router activation or real-task transmission occurred at this checkpoint.

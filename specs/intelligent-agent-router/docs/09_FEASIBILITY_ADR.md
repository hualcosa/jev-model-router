# ADR-006 — Shared core, native hooks, and local preparation for encrypted tasks

Status: accepted for implementation by primary technical review, 2026-10-19. This is feasibility acceptance, **not release acceptance** or user approval to transmit real tasks.

## Decision

Use a stdlib-first shared Python core and thin official runtime adapters. Integrate the pinned optional TypeSafe Python SDK 0.7.5 with bounded deadlines; no inference proxy or Node bridge. Root events produce advisory recommendations only; no automatic root model/effort/settings changes. Classify eligible workers once, before deterministic model/effort policy. Default disabled/shadow; provider transmission requires independent consent.

Prefer native PreToolUse plaintext task input (verified Claude). Codex 0.163.0 worker message is opaque at native PreToolUse, so a hook-only classifier cannot honestly implement task-aware routing there. Use a local MCP preparation tool with ordinary plaintext schema, followed by native spawn with a decision reference in the ordinary task_name. The root supplies task text, not model/effort; the shared core owns the route. Do not decrypt private arguments, inspect credentials, intercept inference or treat task-name keywords as classification.

Production reference design: cryptographically random, bounded native-valid name, local private storage, canonical project/session scoping, short TTL, atomic one-time consumption, replay protection. Missing/expired/wrong-session reference, unavailable provider, unknown capability, custom/unknown profile, or any existing non-null model/effort (including empty string) means unchanged input. These controls are **requirements, not implemented by the static P0 fixture**. Prepared references must never authorize tools, widen sandbox/permissions, or override pins.

Binding is explicitly `orchestrator_attested`: there is no supported cryptographic comparison between prepared plaintext and native encrypted message. Treat routing as optimization, never as a security/content-authorization boundary. Preparation adds one tool round trip and depends on root compliance; measure omission/latency in evaluation. Generic guidance must require original task unchanged and omission of model/effort. Omitted preparation preserves native inheritance, not silent fallback guesses.

## Verified capability matrix

| Surface | Task input | Effective child route | Root unchanged | Remaining gates |
|---|---|---|---|---|
| Claude CLI 2.1.303 | Native plaintext | Haiku/Medium, actual modelUsage + lifecycle | Sonnet/High | Full catalog/policy, conflicts, permission matrix |
| Codex CLI 0.163.0 TUI | Worker opaque; root plaintext | Luna/Medium, native lifecycle + last typed host contexts | Sol6.1/Low | Production reference bridge and full permission matrix |
| Codex CLI 0.163.0 exec hybrid | Local MCP plaintext then opaque native spawn, same run | Luna/Medium, lifecycle + last host turn_context | Sol6.1/Low | Fixture static; no TTL/session/replay implementation; exec used never approvals/read-only |
| Claude desktop 2.42304.2 | Unknown in actual app session | Not tested | Not tested | Mandatory separate desktop smoke |
| Codex desktop 26.1013.40934 / embedded 0.163.0-alpha.10.2 | Source suggests encryption; actual app untested | Not tested | Not tested | Mandatory separate desktop smoke; no CLI parity assumption |
| TypeSafe/Jev SDK 0.7.5 | SDK MockTransport plus one live synthetic task | Valid jev-1.13.0 response, 533.48ms client elapsed | N/A | Representative accuracy/latency evaluation pending; real-task consent absent |

Native Codex TUI inherited on-request/read-only; the separate hybrid exec used never/read-only and hook permission_mode bypassPermissions. Neither establishes deny/ask/conflicting-hook preservation. Codex fixture emitted allow for target spawn; production emission is release-gated on proving no permission widening. If safe application cannot be established, that mode abstains/advises rather than allow-bypassing restrictions.

Availability of requested models is user-assumed; exact runtime IDs, versions, supported efforts and actual execution remain distinct verified technical facts. Fable5.1/Luna6/Terra6/Sol6.1/Astra6 are policy targets, not proof of every runtime mapping. Unknown mapping abstains; no silent generation substitutions.

## Evidence and acceptance

- ../evidence/p0/claude-cli-spike-replay.json — strict single-run native Claude proof.
- ../evidence/p0/codex-cli-spike.json — native TUI worker model/effort, inherited sandbox/approvals.
- ../evidence/p0/codex-hybrid-spike.json — strict same-run local preparation + hook composition; no provider calls.
- ../evidence/p0/codex-source-audit.md — exact source references and encryption limitation.
- ../evidence/p0/jev-sdk-audit.md and jev-live-readiness.json — SDK contract plus original live blocker, now resolved by jev-live-synthetic.json (one synthetic request only).

RTE-006 closes the early feasibility gate and permits core implementation. It does not close desktop, privacy, classifier quality/latency, permission, installer/rollback or E2E acceptance gates. RTE-044 release still depends on both desktop surfaces and the complete backlog acceptance criteria. No global installation or real-project transmission is authorized by this ADR.

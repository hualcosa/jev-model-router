# Installed global worker verification — 2026-10-19

**Later update:** Claude global automatic CLI routing now passed installed native
worker, explicit-pin and competing-classic-hook tests. See
[33 — Claude production activation](33_CLAUDE_PRODUCTION_ACTIVATION.md) for current
state and scoped limits. The incomplete Claude investigation below is retained
as historical evidence, not the current activation status.

## Codex: successful policy selection and native worker execution

The user asked to activate and verify automatic subagent model selection. The
existing global `auto_workers` installation was exercised, not replaced by an
injected test hook or a fake classifier.

One frozen synthetic assignment (TASK-011) was prepared once through the
registered native `intelligent_router.prepare_task` tool. Jev returned T1,
confidence **0.83**, and policy selected **GPT-6.1 Sol / medium**. One scoped
reference was issued and consumed by one unpinned native spawn.

Evidence from the actual installed package:

- `spawn` telemetry recorded one `rewrite_emitted`.
- Native `PostToolUse` observed the selected model and effort arguments.
- `SubagentStart` and `SubagentStop` reported Sol with the same child identity.
- The synthetic child's session metadata linked it to the exact test parent
  before its `turn_context` was inspected. The child actually ran Sol / medium,
  approval policy `never`, sandbox `read-only`, in the scratch cwd.
- The parent remained Sol / medium, `never`, `read-only`, in that same cwd.
- One provider classification and one completed worker; no confidence reroll,
  threshold change, forced route, permission grant or root switch.

This is a positive global installed-worker routing test. Because policy chose
the same model as the parent, it is **not** evidence of a different-model
downgrade or cost savings. The imaginary codebase's task implementation was not
the test objective; the child reported no edits or shell use.

Sanitized results: `../evidence/p1/global-worker-verification.json`.
Raw synthetic stream: the global Codex private directory's
`verify-worker-011.jsonl` and stderr companion. No real project transcript was
read to gather this evidence. Fourteen adapter and sixteen profile tests also
passed during this verification; the last full SDK-required suite passed 719.

## Claude: activation remains technically incomplete

The current Python command-hook adapter's bootstrap has no verified
originating-session conflict authority, so it intentionally cannot rewrite
worker routing in `auto_workers`. Switching its JSON mode alone would not
activate the feature. The installed global configuration remains `warn`.

A new bounded investigation found a genuine native integration point: mods can
handle `agent.spawn` before worker-model resolution. That does not by itself
establish absence of competing active handlers. Documented settings reads and
fresh-process `get_hooks_listing` do not enumerate the original session's
effective dynamic registrations; `plugin.register` cannot establish all earlier
admitted handlers. No safety guard was removed and no successful Claude
automatic routing claim follows from the Codex test above.

Current references:
- [Claude mods subagents](https://code.claude.com/docs/en/plugins/mods/reference#subagents)
- [Claude mods API](https://code.claude.com/docs/en/plugins/mods/api)
- [Native mod ordering and settings hooks](https://code.claude.com/docs/en/plugins/mods/events#where-settings-hooks-run-in-the-order)

These remaining integration requirements are implementation work, not another
missing user authorization. Desktop and all-model/all-permission-mode coverage
remain outside the evidence above.

### Exact installed Claude build probe

A bounded isolated probe used the installed **2.1.303** binary (SHA256
`d2da3b003dc08b88b7230469014fe3e1dc6fe94bc8f648e89b34175d30269370`).
Two native offline middleware tests passed: an unpinned `agent.spawn` was
rewritten to Haiku, and an explicit Opus selection remained unchanged. The test
also asserted that parent model, permission mode and spawn identity were
preserved. Its terminal handler was stubbed, so **no real worker or inference
was executed by these tests**. Network and real-home reads were denied by the
probe's macOS sandbox; no repository or user configuration was edited.

Supported offline loading and metadata-only initialization produced no type
declarations. Read-only extraction from the binary yielded its embedded
651,852-byte declarations (SHA256
`8afa71883ecfa52901eb7a04cf31fef700d8ba565eaad244f4884cc620f8d56e`).
They confirm that `settings.read` includes flag settings, but expose no complete
same-session dynamic hook/mod registry. This is not supported type generation
and is not a claim that an undocumented internal method is a public API.

The probe establishes a feasible native interception primitive, **not a finished
production Claude adapter**. Its temporary module was not installed as the real
router. Under the existing conflict-safety requirement, Claude remains in
advisory mode; silently setting `conflicts_checked=true` would only hide the
missing implementation. No additional consent question can replace that check.

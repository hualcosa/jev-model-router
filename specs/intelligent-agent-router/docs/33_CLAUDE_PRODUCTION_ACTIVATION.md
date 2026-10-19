# Claude global production activation — 2026-10-19

This supersedes the historical Claude `warn` / incomplete-activation status in
documents 31 and 32. The CLI integration is now installed, enabled and exercised
through **real native workers and real Jev**, not a fixture classifier.

## Current state

- Claude Code **2.1.303**, user-scope plugin
  `intelligent-agent-router@intelligent-router-local-0eca8ee6fabe`, version
  **0.1.0+34ea84ea5c74**.
- External global configuration: `mode: auto_workers`, real and synthetic task
  consent enabled. Root model/effort and native permissions are not changed.
- Updated using native `plugin marketplace update` and `plugin update`, **without
  uninstalling**. The durable distribution remains `global/claude/marketplace-v2`;
  the former directory and private configuration/metadata backups are retained.
- The router is first in `enabledPlugins` insertion order, so it observes the
  other user mod's admission. All parsed settings values are unchanged; no other
  plugin was disabled. Fresh native initialization verified the actual order.
- Start a **new Claude session** to load the updated module. Ordinary root-only
  turns do not demonstrate worker routing. Explicit worker model/effort pins and
  custom profiles intentionally bypass automatic selection.

## Native integration and conflict protection

The original Python command-hook bootstrap still does **not** claim complete
originating-session hook inventory. Its conservative guard was not flipped.

The new native `classic.PreToolUse` middleware instead awaits `next(e)` exactly
once and inspects the **actual final classic batch outcome** for that call. It
preserves ask/deny/allow, additional context and effective nonrouting arguments.
Pins on either the original input or final classic input cause abstention before
Jev. Only an eligible worker receives the policy-selected model/effort proposal.
No `allow` is added, so this path does not require a permission-mode grant.

Authority is exact-build and exact-module-set scoped: the measured binary SHA,
complete initial module list, initial Ponytail admission/version, and audited
Ponytail manifest/native-hook entrypoints/band-source digest must match.
Ponytail's Agent/Task `tool.call` path is a transparent `next(e)`; the measured
remaining three modules are native builtins of that pinned binary. Initial
collection and later invalidation are separate phases. Unknown modules, changed
versions, late registrations or rebuilds invalidate routing; generation is
checked again after the provider returns. The native reload contract rebuilds
all modules when one hooks `engine.create`/`plugin.register`; own-only reload
snapshots do not grant authority.

The installed-copy bridge uses `$.plugin.root` and public `$.process.run` argv,
not a development checkout, shell interpolation, executable replacement or
private runtime method. It reuses per-project consent narrowing, minimization,
policy, catalog, persistent run-once state and safe telemetry. The key remains
external. Provision the private state parent during installation; the state
store intentionally creates only its private leaf.

## Installed global acceptance test

One fresh native session used the installed global copy, **without `--plugin-dir`**:

| Case | Original worker input | Effective execution |
| --- | --- | --- |
| Automatic | No model/effort pins; frozen synthetic TASK-011 | **Sonnet 5.5 / medium** |
| Explicit pin | Sonnet / high | **Sonnet 5.5 / high**, unchanged |
| Classic conflict | Unpinned; separate classic test hook selected Haiku / high | **Haiku 5.5 / high**, router abstained |

The main session remained **Opus 5.5 / high** before and after all three workers.
Permission mode stayed `auto`; no permission or sandbox setting was changed.
Native Pre/PostToolUse and matching child identities/transcripts independently
confirmed arguments, actual model and actual effort. A duplicate native stop
for the conflict worker was correlated by identity, not counted as another spawn.

Exactly **one worker Jev call**, confidence **0.82**, selected Sonnet / medium.
Pinned and conflicting workers made **zero worker classifier calls**. All 38
installed payload files matched the content-addressed build manifest. Raw
synthetic evidence is private; sanitized evidence is
[`claude-global-production-verification.json`](../evidence/p1/claude-global-production-verification.json).

Regression checks: **722 Python tests passed**, SDK required, plus **14 Node
middleware tests passed**. Native plugin validation passed. Independent focused
review found an entrypoint-attestation gap; manifest/native-hook bindings and a
regression test were added before installation.

## Limits and rollback

- This is CLI production-routing evidence, **not desktop end-to-end verification**.
  Managed organizations may suppress user-installed classic mod handlers; do not
  bypass that restriction or claim this user-host test covers managed hosts.
- Automatic Claude mapping remains the verified **Haiku 5.5 / Sonnet 5.5 medium**
  catalog. Other mappings/efforts abstain rather than guessing; a pinned high
  worker in this acceptance test is not an automatic high-effort catalog entry.
- Native or companion updates require revalidation. A changed module set/order
  safely disables automatic rewriting. Low confidence or unsupported mappings
  retain normal native inheritance. This does not close broad quality/benchmark,
  all-model or all-surface release gates.
- Set `global/claude/private/config.json` mode to `warn` (advisory) or `disabled`
  (off) to stop automatic routing without uninstalling. For code rollback, the
  prior distribution is `marketplace-v2-before-native-mod-20261019T230729Z`;
  restore the source through a backed-up directory swap and native plugin update,
  not by editing native cache contents or trust hashes. Preserve external state
  and the key. Backups are `private/before-native-mod-20261019T230729Z`.

No commit, push, remote change, desktop control or real-project transcript read
was used for this activation. Codex configuration was not changed by this update.

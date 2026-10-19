# Claude hook inventory: configured candidates are not session authority

## Implemented and measured

`router_core/claude_inventory.py::read_claude_hook_candidates` reads candidate
metadata from Claude Code **2.1.303**, using the version-bound control protocol
exported in official `@anthropic-ai/claude-agent-sdk` **0.3.304** types. This is
not a claim of a stable documented high-level SDK method.

The helper sends only `initialize` and `get_hooks_listing`, with `--bare`, empty
MCP configuration and no tools. It sends no user message and starts no model
turn. Normal startup **can execute SessionStart hooks without a user message**;
therefore `--bare` is essential, not an optimization. Native `system/ui_invalidate`
notifications are accepted; unexpected control requests or turn messages fail.

The reader bounds elapsed time and bytes, rejects duplicate/nonfinite JSON,
checks policy visibility and disabled candidate rows, sanitizes errors, removes
common provider credentials, and kills/reaps its helper. The returned command
text remains private ephemeral display metadata: never log/persist it or parse
it as authoritative raw plugin argv.

Native proof: [`claude-bare-inventory-native.json`](../evidence/p1/claude-bare-inventory-native.json).
The production reader found all three deliberately configured user/project/local
PreToolUse candidates in an isolated home/project, all disabled under bare mode.
A SessionStart sentinel did not execute. No principal configuration, user
messages, model calls or Jev calls were involved. Four adversarial subprocess
tests cover protocol sequence, bounds, malformed messages, timeout, EOF,
policy ambiguity, version gating and cleanup (ResourceWarning treated as error).

## Remaining authority gap (RTE047 stays incomplete)

A fresh helper does **not** observe the running originating session's invocation
overrides, inline plugins or dynamically registered skill/agent hooks. Launch
argv alone cannot reconstruct those dynamic registrations either. Claude hook
stdin does not supply that inventory. Settings resolution is likewise not an
effective originating-session hook inventory.

Official documentation describes [skill and agent hook lifetimes](https://code.claude.com/docs/en/hooks#hooks-in-skills-and-agents).
This is why candidate discovery must not set `conflicts_checked=True` or enable
production Claude capability profiles. Existing native/profile/package guards
are unchanged. No undocumented hook merge order is assumed. The isolated probe
does not establish desktop support or complete effective-session discovery.

Next necessary evidence is inventory from the **actual originating runtime's**
control channel, bound to the relevant session and tool invocation. A controller
or wrapper is an investigation, not an implemented transparent-plugin feature;
it must also satisfy the original desktop requirement. Do not replace native
worker routing with a different product or disable the conflict gate to close
this item.

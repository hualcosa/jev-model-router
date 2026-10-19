# Global activation — 2026-10-19

**Current Claude update:** automatic CLI routing is now installed and verified;
see [33 — Claude production activation](33_CLAUDE_PRODUCTION_ACTIVATION.md).
The older Claude advisory-only verification narrative below is historical.

User authorization now covers real task descriptions across projects in both
Codex and Claude Code. This is a native user-level installation, not a shell
alias or executable replacement. Root model/effort, explicit worker pins and
native filesystem/sandbox settings are unchanged.

## Current installation

| Runtime | Selector marketplace | Installed version | Mode |
| --- | --- | --- | --- |
| Codex CLI 0.163.0 | `intelligent-router-local-0eca8ee6fabe` | `0.1.0+ecd4ce158d73` | `auto_workers` |
| Claude Code 2.1.303 | `intelligent-router-local-0eca8ee6fabe` | `0.1.0+34ea84ea5c74` | `auto_workers` |

Plugin name is `intelligent-agent-router`. Both configurations authorize real
and synthetic tasks. Durable runtime directories are
`~/.local/share/intelligent-agent-router/global/{codex,claude}/`, with private
configurations in `private/config.json`. The shared pinned interpreter and key
file remain outside the plugin; key contents were not packaged or printed.
The original project-bound Codex plugin is retained but disabled to avoid double
classification. No installed legacy Claude router was found; none was disabled.

Global hooks use native process cwd, reject an event claiming a different cwd,
and isolate state/profiles by hashes of lexical and canonical cwd. Ancestor
project configuration applies root-to-cwd and can only narrow its predecessor,
including disabling operation or revoking provider consent. A child directory
cannot bypass a parent revocation. Private files are not written into projects.

Codex obtains/refreshes a project-bound 24h capability profile on SessionStart
using native model/hook metadata. Fresh hook inventory is still checked when
loading authority. Expiry during a session abstains; a new session can refresh
locally without another installation. The global SessionStart hook has a 30s
ceiling to accommodate sequential bounded metadata calls; no provider call is
needed for diagnostics. Other lifecycle timeouts are unchanged.

## Native MCP compatibility workaround

Actual packaged execution exposed a startup failure in bundled MCP transport.
Both plugin-root placeholder spellings remained literal in native transport
metadata and the native client failed initialization; invoking the same installed
server with an absolute path initialized correctly. These failures were not
misreported as successful worker tests.

The exact bundled router MCP entry is disabled through plugin-scoped native
policy. A native user MCP registration named `intelligent_router` points to the
absolute `scripts/router_mcp.py` under the accepted installed Codex version.
Its tool allowlist contains **only `prepare_task`**, with automatic approval for
that allowlisted classification tool following the user's production activation
request. Write/open-world MCP annotations remain truthful. No shell/tool blanket
approval or sandbox change was made. All targeted native config edits have
private backups and parsed-diff checks.

On an update, rebind that native MCP registration to the new accepted
`installedPath`. Do not assume bundled placeholder interpolation works or delete
the pinned installed version while the user MCP still references it.
Codex marketplace source replacements did not uninstall its plugin. Claude's
native marketplace removal **does uninstall its plugins**; when replacing the
new global source, the router was immediately reinstalled. External key/state
were retained. This was an update, not a required normal-use removal cycle.

## Verification and limits

- Full SDK-required offline suite: **719 tests passed** (8.496s), including six
  new global scope/ancestor-revocation cases. After reverting an unsuccessful
  placeholder experiment in source, all 14 packaging tests passed again.
- Read-only independent review found no demonstrated authority/consent bypass;
  its SessionStart timeout finding was corrected before installation.
- Codex root synthetic smoke succeeded in the original repository and a
  different scratch cwd, creating distinct state/profile scopes and one real
  successful Jev assessment per smoke. Low confidence correctly deferred.
- A subsequent real native `intelligent_router.prepare_task` call from the
  installed copy in the other cwd reached Jev and returned `low_confidence`.
  No retry, invented task reference or child spawn occurred. This verifies MCP
  startup/approval/session binding and policy abstention, **not** a successful
  global automatic worker rewrite.
- Claude is installed/enabled at user scope. Its native synthetic print session
  in the other cwd exited successfully with the expected filenames; hook
  telemetry recorded one real Jev success, confidence 0.56, and safe deferral.
- Final installed payload hashes matched BUILD: Codex 34 files, Claude 33 files.

**Claude automatic worker rewriting remains unavailable**: the originating
session's effective hook conflict inventory has not been established. Its
global mode intentionally remains `warn`; no fresh helper or user approval is
misrepresented as proof of that technical capability. Desktop behavior and
in-session MCP workspace rebinding are not verified. Codex still abstains for
unmeasured permission modes and unsupported native model mappings (Terra 6 was
not advertised). Production configuration does not close remaining release or
representative quality/benchmark gates.

Start new native sessions to load the global plugin. To disable without
uninstalling, set the respective external configuration mode to `disabled`.

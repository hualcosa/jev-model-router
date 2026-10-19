"""Version-bound Claude metadata probe; never authority for a live session.

`--bare` suppresses hook execution while retaining candidate hook listings.
The fresh process cannot see invocation-only or ephemeral originating-session
hooks. Callers MUST NOT treat this result as a complete conflict attestation.
Raw listing text is private, ephemeral metadata: do not log or persist it.
"""
import json
import os
import selectors
import signal
import subprocess
import time

from .classifier import _unique
from .inventory import InventoryError, MAX_BYTES

VERIFIED_VERSION = "2.1.303"


def _validate_listing(value):
    if (not isinstance(value, dict) or not isinstance(value.get("bareMode"), dict)
            or not isinstance(value.get("hooks"), list) or len(value["hooks"]) > 1024
            or value.get("errors") not in (None, [])):
        raise InventoryError("claude_inventory_incomplete")
    policy = value.get("policy")
    if (not isinstance(policy, dict)
            or any(type(policy.get(k)) is not bool for k in
                   ("disabledByPolicy", "managedOnly", "pluginOnly", "allDisabled"))
            or type(policy.get("policyHookCount")) is not int
            or policy["policyHookCount"] < 0):
        raise InventoryError("claude_inventory_incomplete")
    if policy.get("policyUnreadable", False) is not False or policy["policyHookCount"] or policy["managedOnly"]:
        raise InventoryError("claude_inventory_policy_ambiguous")
    for row in value["hooks"]:
        if (not isinstance(row, dict) or row.get("disabled") is not True
                or any(not isinstance(row.get(k), str) or len(row[k]) > 65536
                       for k in ("event", "matcher", "source", "type", "commandText"))):
            raise InventoryError("claude_inventory_incomplete")
    return value


def read_claude_hook_candidates(binary, project, *, version=VERIFIED_VERSION, deadline_seconds=10):
    """Read configured candidates, *not* effective originating-session hooks.

    No user messages, turns, SDK execution, trust edits or settings overrides.
    Unknown CLI versions fail before spawning the metadata process.
    """
    if (not isinstance(binary, str) or not os.path.isabs(binary)
            or not isinstance(project, str) or not os.path.isabs(project) or len(project) > 4096
            or version != VERIFIED_VERSION or type(deadline_seconds) not in (int, float)
            or not 0 < deadline_seconds <= 30):
        raise InventoryError("invalid_inventory_input")
    process = None
    selector = selectors.DefaultSelector()
    try:
        end = time.monotonic() + deadline_seconds
        env = os.environ.copy()
        for key in ("CLAUDECODE", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
            env.pop(key, None)
        env["ROUTER_DISABLE"] = "1"
        actual = subprocess.run([binary, "--version"], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=env, timeout=min(2, deadline_seconds), check=True).stdout
        if actual.strip() != (version + " (Claude Code)").encode("ascii"):
            raise InventoryError("host_version_mismatch")
        process = subprocess.Popen([binary, "-p", "--bare", "--input-format", "stream-json",
            "--output-format", "stream-json", "--verbose", "--strict-mcp-config",
            "--mcp-config", '{"mcpServers":{}}', "--tools", ""],
            cwd=project, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=True)
        selector.register(process.stdout, selectors.EVENT_READ)
        buffer, total = b"", 0
        result = None
        for ident, request in (("initialize", {"subtype": "initialize", "hooks": {}}),
                               ("listing", {"subtype": "get_hooks_listing"})):
            message = {"type": "control_request", "request_id": ident, "request": request}
            process.stdin.write((json.dumps(message, separators=(",", ":")) + "\n").encode())
            process.stdin.flush()
            while True:
                if time.monotonic() >= end:
                    raise InventoryError("inventory_timeout")
                if b"\n" not in buffer:
                    if not selector.select(max(0, end - time.monotonic())):
                        raise InventoryError("inventory_timeout")
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        raise InventoryError("inventory_eof")
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise InventoryError("inventory_size_limit")
                    buffer += chunk
                    continue
                line, buffer = buffer.split(b"\n", 1)
                envelope = json.loads(line, object_pairs_hook=_unique,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                # Native metadata registration can invalidate UI listings before
                # its control reply. This notification has no execution request.
                if (isinstance(envelope, dict) and envelope.get("type") == "system"
                        and envelope.get("subtype") == "ui_invalidate"):
                    continue
                # Refuse unexpected requests/turns instead of responding to them.
                if not isinstance(envelope, dict) or envelope.get("type") != "control_response":
                    raise InventoryError("claude_inventory_unexpected_message")
                response = envelope.get("response")
                if (not isinstance(response, dict) or response.get("request_id") != ident
                        or response.get("subtype") != "success"
                        or not isinstance(response.get("response"), dict)):
                    raise InventoryError("inventory_request_failed")
                result = response["response"]
                break
        return _validate_listing(result)
    except InventoryError:
        raise
    except Exception:
        raise InventoryError("claude_inventory_unavailable") from None
    finally:
        selector.close()
        if process is not None:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    # macOS can report EPERM for a process group whose leader
                    # exited between poll and killpg. Reap that race normally.
                    if process.poll() is None:
                        process.kill()
            # Do not communicate(): an untrusted peer could flood stdout during
            # cleanup. Closing pipes and waiting keeps the read budget bounded.
            for stream in (process.stdin, process.stdout):
                try:
                    stream.close()
                except BrokenPipeError:
                    pass
            process.wait()

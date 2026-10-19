"""Explicit synthetic Codex root advisory smoke; uses an already-trusted fixture.

No hook-definition/trust/global-config changes, Jev calls or transcript parsing.
The temporary hook calls the production core with a deterministic classifier.
"""
import argparse
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.spikes.codex_route_smoke import replaced_files, read_rows
from router_core.inventory import discover_codex_models
from router_core.native import bootstrap_profile
from router_core.privacy import SYNTHETIC_SMOKE


def fixture_source(workspace, state, catalog):
    return f'''import json,sys,pathlib
sys.path.insert(0,{str(ROOT)!r})
from dataclasses import replace
from router_core.catalog import CatalogRegistry
from router_core.config import merge_config_layers
from router_core.native import NativeAdapter,bootstrap_profile
from router_core.state import PrivateStateStore
from router_core.contracts import ProviderResult,ProviderStatus,TaskRequirements
p=pathlib.Path({str(workspace)!r})
def record(value):
 with (p/"root-events.jsonl").open("a") as f:f.write(json.dumps(value)+"\\n")
def classify(description):
 record({{"classification":True,"expected_synthetic":description.text=={SYNTHETIC_SMOKE!r}}})
 return ProviderResult(ProviderStatus.SUCCESS,TaskRequirements(.4,.4,.2,.99,"T1",risk="low"))
profile=replace(bootstrap_profile("codex","cli","0.163.0"),catalog=CatalogRegistry.from_json({catalog!r}))
config=merge_config_layers({{"mode":"warn","consent":{{"synthetic_tasks":True}}}},{{}})
adapter=NativeAdapter(profile,config,PrivateStateStore(pathlib.Path({str(state)!r})),classify,project_id=str(p))
event=json.load(sys.stdin)
if pathlib.Path(event.get("cwd","")).resolve()==p.resolve():
 out=adapter.handle(event)
 record({{"event_name":event.get("hook_event_name"),"model":event.get("model"),
  "effort_present":"effort" in event,"turn_id_present":bool(event.get("turn_id")),
  "expected_prompt":event.get("prompt")=={SYNTHETIC_SMOKE!r},"output":out}})
 if out is not None:print(json.dumps(out))
'''


def summarize(rows, stdout, exit_code, *, tui=False):
    warnings = [r for r in rows if isinstance(r.get("output"), dict) and r["output"].get("systemMessage")]
    calls = [r for r in rows if r.get("classification")]
    prompts = [r for r in rows if r.get("event_name") == "UserPromptSubmit"]
    starts = [r for r in rows if r.get("event_name") == "SessionStart"]
    errors = []
    if len(calls) != 1 or not calls[0].get("expected_synthetic"):
        errors.append("expected_one_synthetic_classification")
    if len(prompts) != 1 or not prompts[0].get("expected_prompt") or not prompts[0].get("turn_id_present"):
        errors.append("native_prompt_identity_unverified")
    if not starts or any(r.get("model") != "gpt-6-luna" for r in starts+prompts):
        errors.append("native_root_model_mismatch")
    visible = False
    # Only official CLI event stream, never a private transcript.
    for line in stdout.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if warnings:
            expected = warnings[0]["output"]["systemMessage"]
            params = row.get("params", {})
            if row.get("method") == "warning" and params.get("message") == expected:
                visible = True
            elif row.get("method") == "hook/completed":
                run = params.get("run", {})
                if run.get("eventName") == "userPromptSubmit" and run.get("status") == "completed" and any(
                        entry.get("kind") == "warning" and entry.get("text") == expected
                        for entry in run.get("entries", []) if isinstance(entry, dict)):
                    visible = True
            elif expected in json.dumps(row, ensure_ascii=False):
                # exec --json can surface warnings as item.completed error items.
                if row.get("type") == "item.completed" and row.get("item", {}).get("type") == "error":
                    visible = True
    if tui:
        text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", stdout)
        visible = "↳ Hook · Router advisory" in text and "gpt-6.1-sol" in text
    if len(warnings) != 1:
        errors.append("expected_one_root_warning")
    elif set(warnings[0]["output"]) != {"systemMessage", "hookSpecificOutput"} or set(warnings[0]["output"]["hookSpecificOutput"]) != {"hookEventName", "additionalContext"}:
        errors.append("unexpected_warning_control_fields")
    if not visible:
        errors.append("warning_not_observed_in_official_stream")
    if exit_code != 0:
        errors.append("native_process_failed")
    return {"status": "passed" if not errors else "unverified", "errors": errors,
            "runtime": "codex", "surface": "cli", "host_version": "0.163.0", "exit_code": exit_code,
            "classification_calls": len(calls), "external_jev_calls": 0,
            "classifier": "deterministic_synthetic_fixture_not_live_Jev",
            "native_root_models": sorted({r.get("model") for r in starts+prompts if isinstance(r.get("model"), str)}),
            "native_root_effort_exposed": any(r.get("effort_present") for r in starts+prompts),
            "warning_count": len(warnings), "warning_observed_in_official_stream": visible,
            "presentation": "interactive_tui" if tui else "exec_json",
            "root_mutation_output": False if len(warnings) == 1 and "unexpected_warning_control_fields" not in errors else None,
            "native_trust_bypassed": False, "native_hook_definitions_changed": False,
            "not_proven": ["desktop", "live Jev advisory", "production launcher installation", "post-execution root effort", "general routing quality"]}


def run_tui(command):
    """Capture a bounded real terminal; exit after the synthetic reply or timeout."""
    import fcntl
    import pty
    import struct
    import termios
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 45, 160, 0, 0))
    process = None
    selector = selectors.DefaultSelector()
    output = bytearray()
    interrupted = False
    try:
        process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave,
            start_new_session=True, env={**os.environ, "TERM": "xterm-256color", "NO_COLOR": "1"})
        os.close(slave); slave = None
        selector.register(master, selectors.EVENT_READ)
        end = time.monotonic()+90
        stop_at = None
        while time.monotonic() < end:
            if selector.select(.2):
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > 2_097_152:
                    break
                if b"\x1b[6n" in chunk:
                    os.write(master, b"\x1b[1;1R")
                if b"\x1b[c" in chunk:
                    os.write(master, b"\x1b[?1;2c")
                text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output.decode("utf-8", "replace"))
                if stop_at is None and "↳ Hook · Router advisory" in text and "gpt-6.1-sol" in text:
                    # This presentation-only smoke ends after the warning is
                    # rendered; it does not claim the model's task completed.
                    os.write(master, b"\x03")
                    stop_at = time.monotonic()+1
            if stop_at is not None and time.monotonic() >= stop_at:
                os.write(master, b"\x03")
                stop_at = time.monotonic()+1
            if process.poll() is not None:
                break
        if process.poll() is None:
            interrupted = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        return output.decode("utf-8", "replace"), "", process.returncode, interrupted
    finally:
        selector.close()
        os.close(master)
        if slave is not None:
            os.close(slave)
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def run(workspace, executable="/opt/homebrew/bin/codex", *, tui=False, app_server=False):
    workspace = workspace.absolute()  # retain original native source identity
    version = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=5, check=True)
    if version.stdout.strip() != "codex-cli 0.163.0":
        return {"status": "unsupported_host"}
    if not (workspace/".codex/hooks.json").is_file() or not (workspace/"hook.py").is_file():
        raise ValueError("existing_reviewed_fixture_required")
    inventory = discover_codex_models(executable, bootstrap_profile("codex", "cli", "0.163.0").spawn)
    user_config = Path.home()/".codex/config.toml"
    user = tomllib.loads(user_config.read_text()) if user_config.exists() else {}
    command = [executable, "exec", "--skip-git-repo-check", "--json", "-C", str(workspace),
        "-m", "gpt-6-luna", "-s", "read-only", "-c", 'approval_policy="never"',
        "-c", 'model_reasoning_effort="medium"', "-c", 'web_search="disabled"']
    if tui:
        command = [executable, "--no-alt-screen", "--no-daemon", "-C", str(workspace), "-m", "gpt-6-luna", "-s", "read-only",
                   "-a", "never", "-c", 'model_reasoning_effort="medium"', "-c", 'web_search="disabled"', "-c", 'mcp_servers={}']
    if app_server:
        command = [executable, "app-server", "--listen", "stdio://", "-c", 'web_search="disabled"',
                   "-c", 'model_reasoning_effort="medium"', "-c", 'mcp_servers={}']
    for name in (() if app_server or tui else set(user.get("mcp_servers", {})) | {"router_synthetic_p0"}):
        if re.fullmatch(r"[A-Za-z0-9_-]+", name) is None:
            raise ValueError("unsupported_fixture_server_label")
        command.extend(["-c", f"mcp_servers.{name}.enabled=false"])
    if not app_server:
        command.append(SYNTHETIC_SMOKE)
    with tempfile.TemporaryDirectory(prefix="root-state-", dir=workspace) as state:
        with replaced_files(workspace, {"hook.py": fixture_source(workspace, state, json.dumps(inventory["catalog"])),
                                         "root-events.jsonl": ""}):
            app_result = None
            if app_server:
                stdout, stderr, app_result = run_app_server(command, workspace)
                exit_code, interrupted = 0 if app_result["turn_status"] == "completed" else 1, app_result["timed_out"]
            elif tui:
                stdout, stderr, exit_code, interrupted = run_tui(command)
            else:
                stdout, stderr, exit_code, interrupted = run_exec(command)
            rows = read_rows(workspace/"root-events.jsonl")
            result = summarize(rows, stdout, exit_code, tui=tui)
            if app_server:
                result["presentation"] = "app_server_warning_channel"
                # App-server is long-lived; turn completion, not daemon exit,
                # is authoritative. It is intentionally terminated afterward.
                result.pop("exit_code")
                result.update(app_result)
            if tui:
                result["not_proven"].append("interactive model turn completion; smoke intentionally exits after warning rendering")
            result["forced_termination"] = interrupted
            if interrupted:
                result["status"] = "unverified"
                result["errors"].append("native_timeout_or_interruption")
            artifacts = Path(tempfile.mkdtemp(prefix="root-advisory-evidence-", dir=workspace))
            for name, content in (("stdout.txt", stdout), ("stderr.txt", stderr), ("events.jsonl", json.dumps(rows))):
                with os.fdopen(os.open(artifacts/name, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), "w") as file:
                    file.write(content)
            result["private_synthetic_artifacts"] = str(artifacts)
            return result


def run_app_server(command, workspace):
    """Explicit inference spike, separate from production's metadata allowlist."""
    errors = tempfile.TemporaryFile()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=errors, start_new_session=True)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    raw, buffer = bytearray(), b""
    thread_id, turn_status = None, None
    timed_out = False
    def send(message):
        process.stdin.write((json.dumps(message)+"\n").encode())
        process.stdin.flush()
    try:
        send({"id": 1, "method": "initialize", "params": {"clientInfo": {
            "name": "router_synthetic_root_smoke", "version": "1.0.0"}, "capabilities": {"experimentalApi": True}}})
        end = time.monotonic()+90
        while time.monotonic() < end and turn_status is None:
            if not selector.select(.2):
                if process.poll() is not None:
                    break
                continue
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                break
            raw.extend(chunk); buffer += chunk
            if len(raw) > 2_097_152:
                break
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                message = json.loads(line)
                if message.get("error"):
                    turn_status = "request_failed"
                    break
                if message.get("id") == 1:
                    send({"method": "initialized"})
                    send({"id": 2, "method": "thread/start", "params": {"cwd": str(workspace),
                        "model": "gpt-6-luna", "approvalPolicy": "never", "sandbox": "read-only", "ephemeral": True}})
                elif message.get("id") == 2:
                    thread_id = message["result"]["thread"]["id"]
                    send({"id": 3, "method": "turn/start", "params": {"threadId": thread_id,
                        "input": [{"type": "text", "text": SYNTHETIC_SMOKE}]}})
                elif message.get("method") == "turn/completed" and message.get("params", {}).get("threadId") == thread_id:
                    turn_status = message["params"]["turn"]["status"]
        timed_out = turn_status is None and time.monotonic() >= end
    finally:
        selector.close()
        # A reaped parent does not prove descendants released inherited pipes.
        # Signal the group even when the leader already exited, then bound drain.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.stdout.close()
                process.stdin.close()
                process.wait(timeout=3)
    errors.seek(0)
    stderr = errors.read(65536).decode("utf-8", "replace")
    errors.close()
    return raw.decode("utf-8", "replace"), stderr, {"turn_status": turn_status,
        "app_server_process_exit": process.returncode, "timed_out": timed_out}


def run_exec(command):
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=90)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        return "", "", process.returncode, True
    return stdout, stderr, process.returncode, False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-synthetic", action="store_true")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tui", action="store_true", help="capture an actual interactive terminal instead of exec JSON")
    parser.add_argument("--app-server", action="store_true", help="observe the official structured warning notification channel")
    args = parser.parse_args()
    if not args.run_synthetic:
        parser.error("--run-synthetic required; consumes official Codex usage")
    if args.tui and args.app_server:
        parser.error("choose only one presentation surface")
    report = run(args.workspace, tui=args.tui, app_server=args.app_server)
    rendered = json.dumps(report, indent=2)+"\n"
    if args.output:
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())

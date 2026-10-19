#!/usr/bin/env python3
"""Synthetic core/MCP/native Codex smoke in an explicitly trusted scratch.

No inference or file mutation without --run-synthetic and --workspace. Never
bypasses native hook trust. Existing scratch hook/MCP scripts are restored.
Only this test verifier reads synthetic host turn_context for effort evidence;
the production adapter does not consume private transcripts.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import tomllib

TASK = "ROUTER_CORE_SYNTHETIC: Reply exactly ROUTER_SMOKE_OK. Do not use tools or read files."
LIVE_TASK = "Add a unit test showing that an empty search query returns no matches from the existing in-memory search function."
ROOT = Path(__file__).resolve().parents[2]


def fixture_source(workspace, state, *, live_jev=False, sdk_python=None, catalog_json=None):
    source = '''import json,sys,pathlib,time
from dataclasses import replace
sys.path.insert(0, ROOT)
from router_core.config import merge_config_layers
from router_core.native import bootstrap_profile,NativeAdapter
from router_core.state import PrivateStateStore
from router_core.contracts import ProviderResult,ProviderStatus,TaskRequirements
from router_core.preparation import PreparationService
from router_core.mcp import MCPServer
p=pathlib.Path(WORKSPACE).resolve()
profile=replace(bootstrap_profile("codex","cli","0.163.0"),conflicts_checked=True,
 safe_rewrite_permission_modes=frozenset({"bypassPermissions"}))
config=merge_config_layers({"mode":"auto_workers","consent":{"synthetic_tasks":True}}, {})
PROFILE_CATALOG
def record(name,value):
 with (p/name).open("a") as f:f.write(json.dumps(value)+"\\n")
def classify(description):
 record("core-calls.jsonl",{"expected_synthetic":description.text==TASK})
 CLASSIFIER_BODY
adapter=NativeAdapter(profile,config,PrivateStateStore(pathlib.Path(STATE)),classify,
 project_id=str(p),synthetic_tasks=frozenset({TASK}))
def hook():
 e=json.load(sys.stdin)
 if pathlib.Path(e.get("cwd","")).resolve()!=p:return
 out=adapter.handle(e)
 record("core-events.jsonl",{"event":e,"output":out})
 if out is not None:print(json.dumps(out))
class Server(MCPServer):
 def dispatch(self,r):
  out=super().dispatch(r)
  if isinstance(r,dict) and r.get("method")=="tools/call":
   a=r.get("params",{}).get("arguments",{})
   record("core-prep.jsonl",{"expected_synthetic":a.get("task_text")==TASK,
    "opaque":str(a.get("task_text","")).startswith("gAAAA"),"result":out})
  return out
def mcp():Server(PreparationService(adapter)).serve()
'''
    body = 'return ProviderResult(ProviderStatus.SUCCESS,TaskRequirements(0,0,0,.99,"T0",risk="low"))'
    if live_jev:
        if not isinstance(sdk_python, str) or not os.path.isabs(sdk_python) or not isinstance(catalog_json, str):
            raise ValueError("live_jev_fixture_requires_trusted_sdk_and_catalog")
        body = '''from router_core.credentials import load_private_key
 from router_core.classifier import JevClient
 key=load_private_key(pathlib.Path.home()/".config/intelligent-agent-router/jev.env")
 record("core-provider-attempts.jsonl",{"synthetic":True})
 start=time.monotonic()
 result=JevClient(api_key=key,worker_command=(SDK_PYTHON,str(pathlib.Path(ROOT)/"router_core/_jev_worker.py"))).classify(description)
 req=result.requirements
 record("core-provider.jsonl",{"status":result.status.value,"tier":req.tier.value if req else None,
  "confidence":req.confidence if req else None,"risk":req.risk.value if req and req.risk else None,
  "elapsed_ms":round((time.monotonic()-start)*1000,2)})
 return result'''.replace("SDK_PYTHON", repr(sdk_python))
    catalog = ("from router_core.catalog import CatalogRegistry\nprofile=replace(profile,catalog=CatalogRegistry.from_json(" + repr(catalog_json) + "))") if live_jev else ""
    return source.replace("CLASSIFIER_BODY", body).replace("PROFILE_CATALOG", catalog).replace("ROOT", repr(str(ROOT))).replace("WORKSPACE", repr(str(workspace))).replace("STATE", repr(str(state))).replace("TASK", repr(LIVE_TASK if live_jev else TASK))


@contextmanager
def replaced_files(workspace, files):
    originals = {}
    try:
        for name, content in files.items():
            path = workspace/name
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise ValueError("unsafe_fixture_path")
            originals[name] = (path.read_bytes(), path.stat().st_mode & 0o777) if path.exists() else None
            path.write_text(content)
            path.chmod(0o600)
        yield
    finally:
        for name, previous in originals.items():
            path = workspace/name
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(previous[0])
                path.chmod(previous[1])


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def synthetic_context(path, workspace):
    """Test-only last context from the transcript supplied by native hooks."""
    if not isinstance(path, str):
        return {}
    p = Path(path)
    if p.suffix != ".jsonl" or not p.is_file() or p.stat().st_size > 10_000_000:
        return {}
    contexts = [r["payload"] for r in read_rows(p) if r.get("type") == "turn_context"]
    if not contexts or contexts[-1].get("cwd") != str(workspace):
        return {}
    return {k: contexts[-1].get(k) for k in ("model", "effort", "approval_policy", "sandbox_policy")}


def summarize(rows, preparations, calls, workspace, *, live_jev=False):
    events = [r["event"] for r in rows]
    pre = [r for r in rows if r["event"].get("hook_event_name") == "PreToolUse"
           and r["event"].get("tool_name") == "collaborationspawn_agent"]
    post = [e for e in events if e.get("hook_event_name") == "PostToolUse"
            and e.get("tool_name") == "collaborationspawn_agent"]
    starts = [e for e in events if e.get("hook_event_name") == "SessionStart" and not e.get("agent_id")]
    stops = [e for e in events if e.get("hook_event_name") == "SubagentStop"]
    children = [e for e in events if e.get("hook_event_name") == "SubagentStart"]
    errors = []
    parent = synthetic_context(starts[0].get("transcript_path"), workspace) if starts else {}
    child = synthetic_context(stops[0].get("agent_transcript_path"), workspace) if stops else {}
    if len(pre) != 1 or len(post) != 1 or len(stops) != 1:
        errors.append("expected_one_native_spawn")
    if len(preparations) != 1 or not preparations[0].get("expected_synthetic") or preparations[0].get("opaque"):
        errors.append("plaintext_preparation_missing_or_repeated")
    if len(calls) != 1 or not calls[0].get("expected_synthetic"):
        errors.append("expected_one_synthetic_classification")
    if parent != {"model": "gpt-6.1-sol", "effort": "low", "approval_policy": "never", "sandbox_policy": {"type": "read-only"}}:
        errors.append("parent_context_unknown_or_changed")
    expected_model = "gpt-6.1-sol" if live_jev else "gpt-6-luna"
    if child != {"model": expected_model, "effort": "medium", "approval_policy": "never", "sandbox_policy": {"type": "read-only"}}:
        errors.append("child_route_or_permission_context_mismatch")
    if not stops or (not stops[0].get("last_assistant_message", "").strip() if live_jev else stops[0].get("last_assistant_message", "").strip() != "ROUTER_SMOKE_OK"):
        errors.append("child_reply_mismatch")
    if len(children) != 1 or children[0].get("model") != expected_model or not stops or stops[0].get("model") != expected_model:
        errors.append("native_child_model_missing_or_mismatch")
    opaque = False
    if pre:
        original = pre[0]["event"].get("tool_input", {})
        opaque = str(original.get("message", "")).startswith("gAAAA")
        output = (pre[0].get("output") or {}).get("hookSpecificOutput", {})
        updated = output.get("updatedInput", {})
        if any(k in original for k in ("model", "reasoning_effort")):
            errors.append("original_spawn_pinned")
        try:
            prepared = json.loads(preparations[0]["result"]["result"]["content"][0]["text"])
            if prepared.get("ok") is not True or original.get("task_name") != prepared.get("task_name"):
                errors.append("prepared_reference_not_bound_to_spawn")
        except (KeyError, IndexError, ValueError, TypeError):
            errors.append("preparation_reference_unverified")
        if {k: v for k, v in updated.items() if k not in ("model", "reasoning_effort")} != original:
            errors.append("nonrouting_fields_changed")
        if updated.get("model") != expected_model or updated.get("reasoning_effort") != "medium" or output.get("permissionDecision") != "allow":
            errors.append("core_rewrite_missing")
        if not opaque:
            errors.append("expected_opaque_native_message")
        if post and post[0].get("tool_input") != updated:
            errors.append("host_did_not_observe_rewrite")
    return {"runtime": "codex", "host_version": "0.163.0", "surface": "cli",
        "fixture": "shared_core_preparation_mcp_policy_state_native_adapter",
        "status": "passed" if not errors else "unverified_or_failed", "errors": errors,
        "classification_calls": len(calls), "preparation_calls": len(preparations),
        "native_spawn_calls": len(pre), "native_message_opaque": opaque,
        "external_jev_calls": 0, "parent": parent, "child": child,
        "actual_model_source": "native SubagentStart/Stop and synthetic host turn_context",
        "effort_permission_source": "test-only synthetic turn_context; never parsed by production adapter",
        "not_proven": ["live Jev E2E", "desktop", "on-request approval compatibility", "all model versions", "other hook coexistence", "cryptographic equality of prepared and opaque task"]}


def run_synthetic(workspace, executable="/opt/homebrew/bin/codex", *, live_jev=False, sdk_python=None):
    # Preserve the reviewed native hook source spelling. macOS /var and
    # /private/var resolve to one directory but are distinct hook source IDs.
    # Do not silently move an existing trust definition to the canonical alias.
    workspace = workspace.absolute()
    check = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=5, check=True)
    if check.stdout.strip() != "codex-cli 0.163.0":
        return {"status": "unsupported_host", "external_jev_calls": 0}
    # Do not register new hooks, alter native trust records, or touch global config.
    hooks = workspace/".codex/hooks.json"
    config = workspace/".codex/config.toml"
    if not hooks.is_file() or not config.is_file() or "mcp_probe.py" not in config.read_text():
        raise ValueError("existing_trusted_fixture_required")
    catalog_json = None
    if live_jev:
        if not isinstance(sdk_python, str) or not os.path.isabs(sdk_python) or not os.access(sdk_python, os.X_OK):
            raise ValueError("explicit_pinned_sdk_python_required")
        sys.path.insert(0, str(ROOT))
        from router_core.inventory import discover_codex_models
        from router_core.native import bootstrap_profile
        inventory = discover_codex_models(executable, bootstrap_profile("codex", "cli", "0.163.0").spawn)
        catalog_json = json.dumps(inventory["catalog"])
    with tempfile.TemporaryDirectory(prefix="core-state-", dir=workspace) as state:
        files = {"_core_fixture.py": fixture_source(workspace, Path(state), live_jev=live_jev, sdk_python=sdk_python, catalog_json=catalog_json),
                 "hook.py": "from _core_fixture import hook\nhook()\n",
                 "mcp_probe.py": "from _core_fixture import mcp\nmcp()\n",
                 "core-events.jsonl": "", "core-prep.jsonl": "", "core-calls.jsonl": "",
                 "core-provider.jsonl": "", "core-provider-attempts.jsonl": ""}
        with replaced_files(workspace, files):
            prompt = ("Synthetic integration test only. Do not run shell, read files, use network tools, or modify anything. "
                "Use router_synthetic_p0.prepare_task exactly once with the current native session_id from SessionStart context, "
                f"task_id=core_smoke and task_text={json.dumps(LIVE_TASK if live_jev else TASK)}. If preparation fails, report failure and STOP. "
                "If ok, use native spawn_agent exactly once with the returned task_name and the original task_text as message, "
                "omit model/reasoning_effort and omit agent_type. Wait for that worker, then reply DONE. No other tasks.")
            # Persisted project/hook trust lives in user config. Do not ignore
            # it, recreate it through CLI overrides, or use trust-bypass flags.
            # Disable unrelated MCP servers for this invocation only.
            user_config = Path.home()/".codex/config.toml"
            user = tomllib.loads(user_config.read_text()) if user_config.exists() else {}
            if user.get("hooks", {}).get("PreToolUse"):
                raise ValueError("competing_global_rewrite_requires_review")
            user_hooks = Path.home()/".codex/hooks.json"
            if user_hooks.exists() and json.loads(user_hooks.read_text()).get("hooks", {}).get("PreToolUse"):
                raise ValueError("competing_global_rewrite_requires_review")
            command = [executable, "exec", "--skip-git-repo-check", "--json",
                "-C", str(workspace), "-m", "gpt-6.1-sol", "-s", "read-only",
                "-c", 'approval_policy="never"', "-c", 'model_reasoning_effort="low"',
                # User explicitly authorized this synthetic tool call. This
                # override is invocation-only, not a global permission change.
                "-c", 'mcp_servers.router_synthetic_p0.tools.prepare_task.approval_mode="approve"']
            for name in user.get("mcp_servers", {}):
                if name != "router_synthetic_p0":
                    if re.fullmatch(r"[A-Za-z0-9_-]+", name) is None:
                        raise ValueError("unsupported_fixture_server_label")
                    command.extend(["-c", "mcp_servers." + name + ".enabled=false"])
            command.append(prompt)
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, start_new_session=True)
            try:
                stdout, stderr = process.communicate(timeout=120)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    stdout, stderr = process.communicate()
                return {"status": "timeout_or_interrupted", "external_jev_calls": 0}
            report = summarize(read_rows(workspace/"core-events.jsonl"),
                read_rows(workspace/"core-prep.jsonl"), read_rows(workspace/"core-calls.jsonl"), workspace, live_jev=live_jev)
            if live_jev:
                report["external_jev_calls"] = len(read_rows(workspace/"core-provider-attempts.jsonl"))
                report["classifier"] = "live_jev_sdk_0.7.5"
                report["fixture_task"] = "TASK-011_shipped_synthetic"
                report["provider_results"] = read_rows(workspace/"core-provider.jsonl")
                if report["status"] == "passed" and report["external_jev_calls"] == 1:
                    report["not_proven"] = [x for x in report["not_proven"] if x != "live Jev E2E"]
                else:
                    report["status"] = "live_jev_route_unverified_or_deferred"
                report["not_proven"].append("actual task implementation/success; worker must not modify files")
            report["exit_code"] = process.returncode
            report["native_trust_bypassed"] = False
            report["native_hook_definitions_changed"] = False
            artifacts = Path(tempfile.mkdtemp(prefix="core-smoke-evidence-", dir=workspace))
            for name, data in (("stdout.jsonl", stdout), ("stderr.txt", stderr),
                    ("hook-events.jsonl", (workspace/"core-events.jsonl").read_text()),
                    ("preparation.jsonl", (workspace/"core-prep.jsonl").read_text()),
                    ("calls.jsonl", (workspace/"core-calls.jsonl").read_text()),
                    ("provider.jsonl", (workspace/"core-provider.jsonl").read_text())):
                fd = os.open(artifacts/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as file:
                    file.write(data)
            report["private_synthetic_artifacts"] = str(artifacts)
            if process.returncode:
                report["status"] = "native_process_failed"
            # Only bounded status flags; never publish native raw stderr/transcripts.
            report["trust_warning_observed"] = "untrusted" in stderr.lower() or "not trusted" in stderr.lower()
            return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-synthetic", action="store_true")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--live-jev", action="store_true", help="classify shipped TASK-011 through real Jev; no forced confidence or fallback")
    parser.add_argument("--sdk-python", help="absolute interpreter with pinned TypeSafe SDK0.7.5, required for --live-jev")
    args = parser.parse_args()
    if not args.run_synthetic:
        parser.error("--run-synthetic required; consumes official Codex usage")
    if args.live_jev and not args.sdk_python:
        parser.error("--live-jev requires --sdk-python")
    report = run_synthetic(args.workspace, live_jev=args.live_jev, sdk_python=args.sdk_python)
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Reproduce the P0 native Claude spike in a private synthetic workspace.

No inference by default: --run-synthetic is required. This is a feasibility
fixture, NOT the production router, and never installs hooks globally.
"""
import argparse
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

TASK = "Reply with exactly ROUTER_SMOKE_OK. Do not use any tools."
ROOT_MODEL = "claude-sonnet-5-5"
CHILD_MODEL = "claude-haiku-5-5"
MODELS = {"haiku": CHILD_MODEL, "sonnet": ROOT_MODEL, "opus": "claude-opus-5-5"}

# The only rewrite is an unpinned, generic, exact synthetic task in this scratch.
HOOK = '''import json,sys,pathlib
p=pathlib.Path(__file__).resolve().parent
e=json.load(sys.stdin)
if pathlib.Path(e.get("cwd", "")).resolve()!=p:sys.exit(0)
with (p/"events.jsonl").open("a") as f:f.write(json.dumps(e)+"\\n")
if e.get("hook_event_name")=="PreToolUse" and e.get("tool_name") in ("Agent","Task"):
 a=e.get("tool_input",{})
 if a.get("prompt")=="Reply with exactly ROUTER_SMOKE_OK. Do not use any tools." and a.get("subagent_type") in (None,"general-purpose") and a.get("model") is None and a.get("effort") is None:
  b=dict(a);b.update(model="haiku",effort="medium")
  print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse","updatedInput":b}}))
'''


def core_hook():
    """Exact synthetic fixture through real core/adapter/state, no live Jev."""
    root = str(Path(__file__).resolve().parents[2])
    return '''import json,sys,pathlib
from dataclasses import replace
p=pathlib.Path(__file__).resolve().parent
e=json.load(sys.stdin)
if pathlib.Path(e.get("cwd", "")).resolve()!=p:sys.exit(0)
with (p/"events.jsonl").open("a") as f:f.write(json.dumps(e)+"\\n")
sys.path.insert(0, ROOT_PATH)
from router_core.config import merge_config_layers
from router_core.native import bootstrap_profile,NativeAdapter
from router_core.state import PrivateStateStore
from router_core.contracts import ProviderResult,ProviderStatus,TaskRequirements
profile=replace(bootstrap_profile("claude","cli","2.1.303"),conflicts_checked=True,
 safe_rewrite_permission_modes=frozenset({"default","plan","acceptEdits","auto","dontAsk","bypassPermissions"}))
config=merge_config_layers({"mode":"auto_workers","consent":{"synthetic_tasks":True}}, {})
def classify(description):
 with (p/"calls.txt").open("a") as f:f.write("synthetic_call\\n")
 return ProviderResult(ProviderStatus.SUCCESS,TaskRequirements(0,0,0,0.99,"T0",risk="low"))
adapter=NativeAdapter(profile,config,PrivateStateStore(p/"state"),classify,project_id=str(p),
 synthetic_tasks=frozenset({SYNTHETIC_TASK}))
output=adapter.handle(e)
if output is not None:print(json.dumps(output))
'''.replace("ROOT_PATH", repr(root)).replace("SYNTHETIC_TASK", repr(TASK))


def summarize(stream, events, *, root_model=ROOT_MODEL, child_model=CHILD_MODEL, child_alias="haiku"):
    """Only host output counts; no transcript parsing or model self-report."""
    results = [r for r in stream if r.get("type") == "result"]
    final = results[-1] if results else {}
    parents = [e for e in events if e.get("hook_event_name") == "PreToolUse"
               and e.get("tool_name") in ("Agent", "Task") and not e.get("agent_id")]
    posts = [e for e in events if e.get("hook_event_name") == "PostToolUse"
             and e.get("tool_name") in ("Agent", "Task") and not e.get("agent_id")]
    stops = [e for e in events if e.get("hook_event_name") == "SubagentStop" and e.get("agent_id")]
    usage = final.get("modelUsage", {})
    root_efforts = [e["effort"].get("level") if isinstance(e.get("effort"), dict) else None for e in parents + posts]
    child_efforts = [e["effort"].get("level") if isinstance(e.get("effort"), dict) else None for e in stops]
    errors = []
    starts = [e for e in events if e.get("hook_event_name") == "SessionStart"]
    root_messages = [r for r in stream if r.get("type") == "assistant"
                     and "parent_tool_use_id" in r and r["parent_tool_use_id"] is None]
    reported_roots = [r.get("message", {}).get("model") for r in root_messages]
    if (len(starts) != 1 or not reported_roots or any(m != root_model for m in reported_roots)
            or any(e.get("model") is not None and e["model"] != root_model for e in starts)):
        errors.append("root_canonical_identity_missing_or_mismatch")
    scoped = starts + parents + posts + stops
    sessions = [e.get("session_id") for e in scoped + root_messages + results]
    if not sessions or not all(isinstance(s, str) and s and s == sessions[0] for s in sessions):
        errors.append("mixed_or_unknown_native_session")
    if set(usage) != {root_model, child_model}:
        errors.append("unexpected_native_model_aggregate")
    if any(not isinstance(usage.get(model), dict) or type(usage[model].get("outputTokens")) is not int
           or usage[model]["outputTokens"] <= 0 for model in (root_model, child_model)):
        errors.append("native_model_usage_missing_or_zero")
    if final.get("is_error") or not final:
        errors.append("missing_or_failed_native_result")
    if root_model not in usage or child_model not in usage:
        errors.append("effective_model_evidence_missing")
    if not root_efforts or any(e != "high" for e in root_efforts):
        errors.append("root_effort_unknown_or_changed")
    if not child_efforts or any(e != "medium" for e in child_efforts):
        errors.append("child_effort_unknown_or_mismatch")
    if len(parents) != 1 or len(posts) != 1 or len(stops) != 1:
        errors.append("expected_exactly_one_spawn")
    if parents and any(parents[0].get("tool_input", {}).get(k) is not None for k in ("model", "effort")):
        errors.append("original_spawn_was_pinned")
    if parents and posts:
        original = parents[0].get("tool_input", {})
        actual = posts[0].get("tool_input", {})
        if {k: v for k, v in actual.items() if k not in ("model", "effort")} != original:
            errors.append("nonrouting_arguments_changed")
        if actual.get("model") != child_alias or actual.get("effort") != "medium":
            errors.append("rewrite_not_observed_by_host")
    return {"runtime": "claude", "surface": "cli", "fixture": "synthetic_p0_not_production_router",
            "status": "passed" if not errors else "unverified_or_failed", "errors": errors,
            "actual_models_reported": sorted(usage), "root_efforts_reported": root_efforts,
            "session_start_models": [e.get("model") for e in starts],
            "native_root_assistant_models": sorted(set(reported_roots)),
            "root_identity_source": "official root AssistantMessage.message.model, not inferred from requested alias or aggregate",
            "native_model_output_tokens": {m: v.get("outputTokens") for m,v in usage.items() if isinstance(v,dict)},
            "child_efforts_reported": child_efforts, "approval_decision_emitted": False,
            "evidence_source": "native result.modelUsage, Pre/PostToolUse and SubagentStop.effort",
            "not_proven": ["desktop", "Jev", "all model versions", "hook conflicts", "full permissions matrix"]}


def summarize_telemetry(records):
    rows = [r.to_dict() for r in records]
    assessments = [r for r in rows if r["source"] == "assessment"]
    posts = [r for r in rows if r["source"] == "PostToolUse"]
    children = [r for r in rows if r["source"] in ("SubagentStart", "SubagentStop")]
    starts = [r for r in children if r["source"] == "SubagentStart"]
    stops = [r for r in children if r["source"] == "SubagentStop"]
    errors = []
    if not rows or any((r["scope_hash"], r["runtime"], r["host_version"]) !=
                        (rows[0]["scope_hash"], "claude", "2.1.303") for r in rows):
        errors.append("mixed_or_unknown_telemetry_scope")
    if len(starts) == 1 and len(stops) == 1 and starts[0]["agent_hash"] != stops[0]["agent_hash"]:
        errors.append("child_lifecycle_identity_mismatch")
    if len(assessments) != 1 or assessments[0]["data"]["provider_calls"] != 1:
        errors.append("assessment_count_or_provider_evidence_missing")
    if (len(posts) != 1 or posts[0]["data"]["argument_model"] != "haiku"
            or posts[0]["data"]["argument_effort"] != "medium"
            or posts[0]["data"]["actual_execution"] != "unverified"):
        errors.append("argument_versus_actual_separation_missing")
    if len(starts) != 1 or len(stops) != 1:
        errors.append("child_lifecycle_evidence_missing")
    if stops and (stops[0]["data"]["actual_effort"] != "medium"
                  or stops[0]["data"]["actual_execution"] != "reported_by_host"):
        errors.append("child_effort_report_missing")
    if any(r["data"]["actual_model"] is not None or r["data"]["correlation"] != "unverified"
           or r["tool_hash"] is not None or not r["agent_hash"] for r in children):
        errors.append("unsupported_child_model_or_tool_join")
    return {"status": "passed" if not errors else "unverified", "errors": errors,
            "record_count": len(rows), "assessment_count": len(assessments), "post_tool_count": len(posts),
            "child_start_count": len(starts), "child_stop_count": len(stops),
            "actual_child_model": "unverified", "actual_child_effort": "reported_by_host" if not errors else "unverified",
            "tool_to_agent_correlation": "unverified", "root_model_aggregate_not_joined_to_child": True}


def run_synthetic(executable="claude", *, use_core=False, root_alias="sonnet", child_alias="haiku"):
    if root_alias not in MODELS or child_alias not in MODELS or root_alias == child_alias:
        return {"status": "invalid_probe_models"}
    if use_core and (root_alias, child_alias) != ("sonnet", "haiku"):
        return {"status": "unmeasured_core_probe_mapping"}
    version = None
    try:
        check = subprocess.run([executable, "--version"], capture_output=True, text=True,
                               timeout=5, check=True)
        match = re.search(r"\b(\d+\.\d+\.\d+)\b", check.stdout)
        version = match.group(1) if match else None
    except (OSError, subprocess.SubprocessError):
        pass
    if use_core and version != "2.1.303":
        return {"runtime": "claude", "status": "unsupported_core_fixture_host", "network": "none"}
    with tempfile.TemporaryDirectory(prefix="router-claude-route-") as directory:
        scratch = Path(directory).resolve()
        (scratch / "hook.py").write_text(core_hook() if use_core else
            HOOK.replace('b.update(model="haiku",effort="medium")', f'b.update(model="{child_alias}",effort="medium")'))
        command = f'"{sys.executable}" "{scratch / "hook.py"}"'
        hooks = {name: [{"hooks": [{"type": "command", "command": command, "timeout": 5}],
                         **({"matcher": "Agent|Task"} if name in ("PreToolUse", "PostToolUse") else {})}]
                 for name in ("SessionStart", "PreToolUse", "PostToolUse", "SubagentStart", "SubagentStop")}
        settings = scratch / "settings.json"
        settings.write_text(json.dumps({"hooks": hooks, "permissions": {"allow": ["Agent"]}}))
        args = [executable, "-p", "--model", root_alias, "--effort", "high", "--setting-sources", "",
                "--settings", str(settings), "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                "--tools", "Agent", "--no-session-persistence", "--output-format", "stream-json", "--verbose",
                "--include-hook-events", "--system-prompt",
                "Perform only the requested synthetic delegation. Do not access files or network tools.",
                f'Use Agent exactly once with subagent_type general-purpose and prompt "{TASK}". '
                'Omit model and effort. Wait for its result and reply DONE.']
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        proc = subprocess.Popen(args, cwd=scratch, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            stdout, _ = proc.communicate(timeout=90)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as interruption:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()
            return {"runtime": "claude", "status": "interrupted" if isinstance(interruption, KeyboardInterrupt) else "timeout", "network": "official_claude_only"}
        try:
            stream = [json.loads(line) for line in stdout.splitlines() if line.strip()]
            event_path = scratch / "events.jsonl"
            events = [json.loads(line) for line in event_path.read_text().splitlines()] if event_path.exists() else []
            report = summarize(stream, events, root_model=MODELS[root_alias], child_model=MODELS[child_alias], child_alias=child_alias)
        except (ValueError, OSError, TypeError):
            return {"runtime": "claude", "status": "invalid_native_evidence"}
        report["exit_code"] = proc.returncode
        report["host_version"] = version
        report["requested_root_alias"] = root_alias
        report["requested_child_alias"] = child_alias
        if use_core:
            report["host_version"] = version
            report["fixture"] = "core_policy_state_native_adapter_with_injected_synthetic_classifier"
            report["classifier"] = "deterministic_injected_fixture_not_live_Jev"
            calls = scratch / "calls.txt"
            report["classification_calls"] = len(calls.read_text().splitlines()) if calls.exists() else 0
            report["external_jev_calls"] = 0
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
            from router_core.state import PrivateStateStore
            from router_core.telemetry import TelemetryLog
            report["telemetry"] = summarize_telemetry(TelemetryLog(PrivateStateStore(scratch/"state")).read())
            if report["telemetry"]["status"] != "passed":
                report["status"] = "telemetry_unverified"
            if report["classification_calls"] != 1:
                report["status"] = "core_classification_count_mismatch"
        if proc.returncode != 0:
            report["status"] = "native_process_failed"
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-synthetic", action="store_true")
    parser.add_argument("--core-adapter", action="store_true", help="exercise shared core/policy/state instead of static P0 rewrite")
    parser.add_argument("--root-model", choices=tuple(MODELS), default="sonnet")
    parser.add_argument("--child-model", choices=tuple(MODELS), default="haiku")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.run_synthetic:
        parser.error("explicit --run-synthetic is required; this consumes official Claude usage")
    report = run_synthetic(use_core=args.core_adapter, root_alias=args.root_model, child_alias=args.child_model)
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as file:
            file.write(rendered)
    print(rendered, end="")
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())

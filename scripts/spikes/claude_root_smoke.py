#!/usr/bin/env python3
"""Observe actual root hook capability, not SDK-only metadata as a hook fallback.

Explicit synthetic inference only. Never installs global hooks, changes root
selection from a router hook, parses transcripts, or sends anything to Jev.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from router_core.native import bootstrap_profile
from router_core.privacy import SYNTHETIC_SMOKE
from router_core.state import PrivateStateStore
from router_core.telemetry import TelemetryLog


def fixture_source():
    return f'''import hashlib,json,os,pathlib,sys
sys.path.insert(0,{str(ROOT)!r})
from router_core.config import merge_config_layers
from router_core.native import NativeAdapter,bootstrap_profile
from router_core.state import PrivateStateStore
from router_core.contracts import ProviderResult,ProviderStatus,TaskRequirements
p=pathlib.Path(__file__).resolve().parent
e=json.load(sys.stdin)
if pathlib.Path(e.get("cwd","")).resolve()!=p:sys.exit(0)
def record(row):
 fd=os.open(p/"observations.jsonl",os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
 with os.fdopen(fd,"w") as f:f.write(json.dumps(row)+"\\n")
def classify(description):
 record({{"classification":True,"exact_synthetic":description.text=={SYNTHETIC_SMOKE!r}}})
 return ProviderResult(ProviderStatus.SUCCESS,TaskRequirements(.4,.4,.2,.99,"T1",risk="low"))
adapter=NativeAdapter(bootstrap_profile("claude","cli","2.1.303"),
 merge_config_layers({{"mode":"warn","consent":{{"synthetic_tasks":True}}}},{{}}),
 PrivateStateStore(p/"state"),classify,project_id=str(p))
out=adapter.handle(e)
effort=e.get("effort")
level=effort.get("level") if isinstance(effort,dict) else None
record({{"event":e.get("hook_event_name"),"model_present":isinstance(e.get("model"),str),
 "prompt_id_present":bool(e.get("prompt_id")),"exact_synthetic_prompt":e.get("prompt")=={SYNTHETIC_SMOKE!r},
 "session_hash":hashlib.sha256(e.get("session_id","").encode()).hexdigest(),
 "effort":level if level in ("low","medium","high","xhigh","max") else None,"output":out}})
if out is not None:print(json.dumps(out))
'''


def summarize(stream, observations, records, exit_code):
    final = [r for r in stream if r.get("type") == "result"]
    messages = [r for r in stream if r.get("type") == "assistant" and
                "parent_tool_use_id" in r and r["parent_tool_use_id"] is None]
    root_models = sorted({r.get("message",{}).get("model") for r in messages})
    starts = [r for r in observations if r.get("event") == "SessionStart"]
    prompts = [r for r in observations if r.get("event") == "UserPromptSubmit"]
    calls = [r for r in observations if r.get("classification")]
    outputs = [r["output"] for r in observations if isinstance(r.get("output"),dict)]
    decisions = [r.to_dict()["data"] for r in records if r.to_dict()["source"] == "assessment"]
    boundaries = [r.to_dict()["data"] for r in records if r.to_dict()["source"] == "boundary"]
    mutation = any(set(r) - {"systemMessage","hookSpecificOutput"} or
                   set(r.get("hookSpecificOutput",{})) - {"hookEventName","additionalContext"} for r in outputs)
    errors = []
    if exit_code != 0 or len(final) != 1 or final[0].get("is_error"):
        errors.append("native_result_missing_or_failed")
    if (not final or root_models != ["claude-haiku-5-5"]
            or set(final[-1].get("modelUsage",{})) != {"claude-haiku-5-5"}):
        errors.append("native_root_identity_missing_or_changed")
    if len(starts) != 1 or len(prompts) != 1 or not prompts[0].get("exact_synthetic_prompt"):
        errors.append("hook_lifecycle_missing")
    session = final[-1].get("session_id") if final else None
    session_hash = hashlib.sha256(session.encode()).hexdigest() if isinstance(session,str) else None
    if session_hash is None or any(r.get("session_hash") != session_hash for r in observations if r.get("event")):
        errors.append("mixed_or_unknown_native_session")
    if mutation or any(not c.get("exact_synthetic") for c in calls) or len(calls) > 1:
        errors.append("mutation_or_classification_scope_failure")
    warnings = sum(bool(r.get("systemMessage")) for r in outputs)
    model_present = bool(starts and starts[0].get("model_present"))
    prompt_id_present = bool(prompts and prompts[0].get("prompt_id_present"))
    if not model_present and warnings:
        errors.append("unsupported_root_advice")
    return {"status":"unverified" if errors else "observed_degraded" if not model_present or not prompt_id_present else "observed",
            "runtime":"claude","surface":"cli","host_version":"2.1.303","errors":errors,
            "exit_code":exit_code,"native_root_assistant_models":root_models,
            "session_start_model_present":model_present,"user_prompt_id_present":prompt_id_present,
            "classification_calls":len(calls),"external_jev_calls":0,"root_warning_count":warnings,
            "root_mutation_output":bool(mutation),"decision_reasons":[r["reason"] for r in decisions],
            "boundary_results":boundaries,"root_stop_efforts":[r.get("effort") for r in observations if r.get("event")=="Stop"],
            "global_installation":False,"transcript_parsing":False,
            "not_proven":["visible root advisory on cold-start Claude hooks","desktop","live Jev","global plugin install"],
            "notice":"SDK root message is test evidence only; it is not available to the production command hook before submission."}


def run_synthetic(binary="/opt/homebrew/bin/claude"):
    check = subprocess.run([binary,"--version"],capture_output=True,text=True,timeout=5,check=True)
    if not check.stdout.startswith("2.1.303 "):
        return {"status":"unsupported_host"}
    with tempfile.TemporaryDirectory(prefix="router-claude-root-") as directory:
        scratch = Path(directory).resolve()
        (scratch/"hook.py").write_text(fixture_source())
        command = shlex.join([sys.executable,str(scratch/"hook.py")])
        hooks = {name:[{"hooks":[{"type":"command","command":command,"timeout":10}]}]
                 for name in ("SessionStart","UserPromptSubmit","Stop","SessionEnd")}
        settings = scratch/"settings.json"
        settings.write_text(json.dumps({"hooks":hooks}))
        args = [binary,"-p","--model","haiku","--effort","medium","--setting-sources","",
                "--settings",str(settings),"--strict-mcp-config","--mcp-config",'{"mcpServers":{}}',
                "--tools","","--no-session-persistence","--output-format","stream-json","--verbose",
                "--include-hook-events","--system-prompt","Answer only the synthetic request; do not access tools or files.",SYNTHETIC_SMOKE]
        env = os.environ.copy()
        env.pop("CLAUDECODE",None)
        proc = subprocess.Popen(args,cwd=scratch,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                text=True,start_new_session=True)
        try:
            stdout,_stderr = proc.communicate(timeout=90)
        except (subprocess.TimeoutExpired,KeyboardInterrupt):
            try:
                os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                proc.stdout.close()
                proc.stderr.close()
            return {"status":"timeout_or_interrupted","external_jev_calls":0}
        stream = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        path = scratch/"observations.jsonl"
        observations = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        records = TelemetryLog(PrivateStateStore(scratch/"state")).read()
        return summarize(stream,observations,records,proc.returncode)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-synthetic",action="store_true")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if not args.run_synthetic:
        parser.error("--run-synthetic is required")
    report=run_synthetic()
    raw=json.dumps(report,indent=2)+"\n"
    if args.output:
        args.output.write_text(raw)
    print(raw,end="")
    return 1 if report["status"] in ("unverified","unsupported_host","timeout_or_interrupted") else 0


if __name__=="__main__":
    sys.exit(main())

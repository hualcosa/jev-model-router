#!/usr/bin/env python3
"""Offline fixture and real CLI subprocess proof; no native/provider calls.

Only fixture creation writes temporary private state. The explain command itself
must leave every fixture state file and directory unchanged. No credentials.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
from router_core.config import merge_config_layers
from router_core.contracts import ProviderResult,ProviderStatus,TaskRequirements
from router_core.explain import scope_hash_for
from router_core.native import NativeAdapter,bootstrap_profile
from router_core.privacy import SYNTHETIC_SMOKE
from router_core.state import PrivateStateStore
from router_core.telemetry import TelemetryLog


def snapshot(root):
    return (root.stat().st_mtime_ns,{p.name:(p.stat().st_ino,p.stat().st_mtime_ns,p.stat().st_mode,
            hashlib.sha256(p.read_bytes()).hexdigest()) for p in root.iterdir()})


def run():
    with tempfile.TemporaryDirectory(prefix="router-explain-offline-") as directory:
        project=os.path.realpath(directory)
        state=Path(project)/"state"
        calls=[]
        def classify(payload):
            calls.append(payload)
            return ProviderResult(ProviderStatus.SUCCESS,TaskRequirements(0,0,0,.99,"T0",risk="low"))
        adapter=NativeAdapter(bootstrap_profile("claude","cli","2.1.303"),
            merge_config_layers({"mode":"shadow","consent":{"synthetic_tasks":True}},{}),
            PrivateStateStore(state),classify,project_id=project)
        output=adapter.handle({"cwd":project,"session_id":"offline-fixture","hook_event_name":"PreToolUse",
            "permission_mode":"default","tool_name":"Agent","tool_use_id":"call-fixture",
            "tool_input":{"prompt":SYNTHETIC_SMOKE,"description":"PRIVATE_FIXTURE_DESCRIPTION"}})
        if output is not None or len(calls)!=1:
            return {"status":"unverified","reason_code":"seed_not_one_shadow_assessment"}
        row=next(r.to_dict() for r in TelemetryLog(adapter.store).read() if r.to_dict()["source"]=="assessment")
        before=snapshot(state)
        env=os.environ.copy()
        for name in ("TYPESAFE_API_KEY","ANTHROPIC_API_KEY","OPENAI_API_KEY","CLAUDE_CODE_OAUTH_TOKEN","CODEX_API_KEY"):
            env.pop(name,None)
        result=subprocess.run([sys.executable,str(ROOT/"scripts/router_cli.py"),"explain",
            "--state-dir",str(state),"--scope-hash",scope_hash_for("claude",project,"offline-fixture"),
            "--row-id",row["row_id"]],stdin=subprocess.DEVNULL,env=env,cwd="/tmp",
            capture_output=True,text=True,timeout=5)
        report=json.loads(result.stdout)
        item=report["records"][0]
        unchanged=before==snapshot(state)
        valid=(result.returncode==0 and not result.stderr and report["status"]=="explained"
            and report["external_calls"]==0 and not report["state_modified"] and not report["current_runtime_checked"]
            and unchanged and len(calls)==1 and "PRIVATE" not in result.stdout and SYNTHETIC_SMOKE not in result.stdout
            and item["policy_provenance"]=="policy_prior" and item["catalog"]["status"]=="recorded_snapshot")
        return {"status":"passed" if valid else "unverified","scope":"offline native-format core fixture, real CLI subprocess",
            "seed_classifier":"deterministic_injected_not_Jev","seed_classifications":len(calls),
            "external_provider_calls":0,"native_host_calls":0,"explain_reclassification":False,
            "cli_exit_code":result.returncode,"state_bytes_modes_inodes_mtimes_unchanged":unchanged,
            "state_files_verified":sorted(before[1]),"stdin":"DEVNULL","credentials_removed_from_subprocess_env":True,
            "reason":item["record"]["data"]["reason"],"policy_provenance":item["policy_provenance"],
            "saved_catalog_status":item["catalog"]["status"],"current_runtime_checked":False,
            "recommended_model":item["record"]["data"]["recommended_model"],
            "recommended_effort":item["record"]["data"]["recommended_effort"],
            "parent_tool_child_join":"unverified","raw_prompt_or_fixture_description_returned":False,
            "global_activation":False,"notice":"No execution, task-quality, current entitlement or complete-history claim."}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    report=run()
    rendered=json.dumps(report,indent=2)+"\n"
    if args.output:args.output.write_text(rendered)
    print(rendered,end="")
    return 0 if report["status"]=="passed" else 1


if __name__=="__main__":
    sys.exit(main())

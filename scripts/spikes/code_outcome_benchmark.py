#!/usr/bin/env python3
"""Actual synthetic code-generation outcomes, graded only in offline Docker.

This advances RTE037; direct native executors are NOT installed worker hooks,
native child inheritance or representative human acceptance evidence.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.spikes.code_grader import grade_python
from scripts.spikes.code_tasks import TASKS
from scripts.spikes import task_outcome_pilot as strategies
from router_core.credentials import load_private_key

IMAGE = "sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3"
CODE_SCHEMA = {"type": "object", "additionalProperties": False,
               "properties": {"source": {"type": "string"}}, "required": ["source"]}


def validate_fixtures(image):
    results = {}
    for task in TASKS:
        positive = grade_python(task["reference"], task["tests"], image=image)
        negative = grade_python(task["broken"], task["tests"], image=image)
        results[task["id"]] = {"reference": positive, "broken": negative}
        if (not positive["passed"] or positive["tests_run"] != 5 or negative["passed"]
                or negative["status"] != "failed" or not positive["cleanup_verified"]
                or not negative["cleanup_verified"]):
            raise ValueError("fixture_validation_failed")
    return results


def code_trial(task, arm, repeat, binary, key, image):
    started = time.perf_counter_ns()
    selected = strategies.trial(task, arm, repeat, binary, key, strategy_only=True)
    prompt = (task["description"]+"\nExact contract:\n"+task["contract"]+
        "\nReturn the complete solution.py source in the source field, without Markdown fences. "
        "Do not execute anything. No tools, network, delegation or file access. "
        "Implement only the requested public function and necessary helpers/imports.")
    with tempfile.TemporaryDirectory(prefix="router-code-executor-") as directory:
        execution = strategies.native(binary, directory, prompt, CODE_SCHEMA, selected["requested"])
    source = execution.get("answer", {}).get("source")
    if execution["status"] == "completed" and isinstance(source, str):
        try:
            grading = grade_python(source, task["tests"], image=image)
            if grading["passed"] and (grading.get("tests_run") != 5 or not grading.get("cleanup_verified")):
                grading = {**grading, "passed": False, "status": "test_count_or_cleanup_mismatch"}
        except (ValueError, UnicodeError):
            grading = {"passed": False, "status": "invalid_source", "tests_run": None,
                       "cleanup_verified": True}
    else:
        grading = {"passed": False, "status": "no_candidate", "tests_run": None,
                   "cleanup_verified": True}
    return {"task_id": task["id"], "arm": arm, "repeat": repeat, **selected,
        "execution": execution, "grading": grading, "oracle_success": grading["passed"],
        "total_ms": (time.perf_counter_ns()-started)/1_000_000,
        "orchestrator_execution_attempts": 1, "orchestrator_retries": 0,
        "native_or_provider_internal_retries": "not_observed", "human_rework": None}


def metadata(image):
    return {"schema_version": 1, "status": "running",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "scope": "self_authored_code_generation_frozen_tests_direct_executor_not_native_worker_integration",
        "host_version": "2.1.303", "runtime": "claude", "image": image,
        "parent_baseline": strategies.BASELINE, "arms": list(strategies.ARMS), "repeats": 2,
        "fixture_sha256": hashlib.sha256((ROOT/"scripts/spikes/code_tasks.py").read_bytes()).hexdigest(),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "grader_sha256": hashlib.sha256((ROOT/"scripts/spikes/code_grader.py").read_bytes()).hexdigest(),
        "strategy_harness_sha256": hashlib.sha256(Path(strategies.__file__).read_bytes()).hexdigest(),
        "not_measured": ["human_review/correction/rework", "representative_real_project_quality",
            "native_child_selection/inheritance", "installed_hook_routing", "Codex", "desktop",
            "subscription_quota/cost_savings", "adversarially_tamper_proof_judging"], "rows": []}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-fixtures", action="store_true")
    mode.add_argument("--run-synthetic", action="store_true")
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--binary", default="/opt/homebrew/bin/claude")
    parser.add_argument("--image", default=IMAGE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.run_synthetic != (args.key_file is not None):
        parser.error("--key-file required only with --run-synthetic")
    result = metadata(args.image)
    result["fixture_validation"] = validate_fixtures(args.image)
    if args.validate_fixtures:
        result["status"] = "fixtures_validated_no_model_calls"
        args.output.write_text(json.dumps(result, indent=2)+"\n")
        return 0
    if subprocess.check_output([args.binary, "--version"], text=True).strip().split()[0] != "2.1.303":
        parser.error("unmeasured native host")
    key = load_private_key(args.key_file)
    jobs = [(task, arm, repeat) for repeat in range(2) for task in TASKS for arm in strategies.ARMS]
    random.Random(901).shuffle(jobs)
    def checkpoint():
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    checkpoint()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(code_trial, task, arm, repeat, args.binary, key, args.image):
                   (task, arm, repeat) for task, arm, repeat in jobs}
        for future in as_completed(futures):
            try:
                row = future.result()
            except Exception:
                # Unexpected runner errors keep a denominator row, not a silent
                # retry or a batch which appears to have fewer/easier tasks.
                task, arm, repeat = futures[future]
                row = {"task_id": task["id"], "arm": arm, "repeat": repeat,
                    "oracle_success": False, "status": "internal_runner_error",
                    "total_ms": None, "jev_callback_attempts": None,
                    "execution": {"status": "not_observed"}, "selection": {}, "human_rework": None}
            result["rows"].append(row)
            checkpoint()
            print(json.dumps({"completed": len(result["rows"]), "total": len(jobs)}), flush=True)
    if any(row.get("status") == "internal_runner_error" for row in result["rows"]):
        result["status"] = "incomplete_runner_errors"
    else:
        result["summary"] = strategies.summarize(result["rows"])
        result["status"] = "code_slice_measured_not_release_validation"
    checkpoint()
    return 0 if result["status"] == "code_slice_measured_not_release_validation" else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Opt-in four-strategy synthetic code-review outcome pilot, not release proof.

No generated code executes. Trusted oracles check native model answers. Direct
CLI executors compare selection strategies, NOT native worker-hook integration.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/"plugins/claude-model-router-hook/hooks"))

from router.config import DEFAULTS
from router.policy import target_for_class
from router.taxonomy import classify_heuristic
from router_core.classifier import JevClient, _unique
from router_core.config import merge_config_layers
from router_core.contracts import EventKind, TaskEnvelope
from router_core.credentials import load_private_key
from router_core.native import bootstrap_profile
from router_core.policy import PolicyScope, assess
from scripts.spikes.code_grader import _capture

FIXTURES = ROOT/"tests/fixtures/intelligent-router/task-outcomes-pilot.json"
BASELINE = {"model": "sonnet", "effort": "medium"}
ARMS = ("original_heuristic", "jev_policy", "parent_selection", "no_router_parent_baseline")
ANSWER_SCHEMA = {"type": "object", "additionalProperties": False,
    "properties": {"bug_line": {"type": "integer"},
        "counterexample": {"type": "object", "additionalProperties": False,
            "properties": {"values": {"type": "array", "items": {"type": "integer"}},
                           "target": {"type": ["integer", "null"]}}, "required": ["values", "target"]},
        "expected_json": {"type": "string"}, "actual_json": {"type": "string"}},
    "required": ["bug_line", "counterexample", "expected_json", "actual_json"]}
SELECTION_SCHEMA = {"type": "object", "additionalProperties": False,
    "properties": {"model": {"type": "string", "enum": ["haiku", "sonnet"]},
                   "effort": {"type": "string", "enum": ["medium"]}}, "required": ["model", "effort"]}


def decode(text):
    return json.loads(text, object_pairs_hook=_unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def oracle(task_id, example):
    if not isinstance(example, dict) or set(example) != {"values", "target"}:
        raise ValueError("invalid_counterexample")
    values, target = example["values"], example["target"]
    if (not isinstance(values, list) or len(values) > 32
            or any(type(x) is not int or not -100 <= x <= 100 for x in values)):
        raise ValueError("invalid_counterexample")
    if task_id == "strict-positive":
        if target is not None:
            raise ValueError("invalid_counterexample")
        return (next((x for x in values if x > 0), None), next((x for x in values if x >= 0), None))
    if task_id == "stable-dedupe":
        if target is not None:
            raise ValueError("invalid_counterexample")
        return list(dict.fromkeys(values)), sorted(set(values))
    if task_id == "binary-search-boundary":
        if type(target) is not int or not -100 <= target <= 100 or values != sorted(set(values)):
            raise ValueError("invalid_counterexample")
        expected = values.index(target) if target in values else -1
        lo, hi, actual = 0, len(values)-1, -1
        while lo < hi:
            mid = (lo+hi)//2
            if values[mid] == target:
                actual = mid
                break
            if values[mid] < target:
                lo = mid+1
            else:
                hi = mid-1
        return expected, actual
    raise ValueError("unknown_task")


def grade(task, answer):
    try:
        if (not isinstance(answer, dict) or set(answer) != set(ANSWER_SCHEMA["required"])
                or type(answer["bug_line"]) is not int or answer["bug_line"] != task["bug_line"]):
            return False
        expected, actual = oracle(task["id"], answer["counterexample"])
        if any(not isinstance(answer[k], str) or len(answer[k]) > 1024 for k in ("expected_json", "actual_json")):
            return False
        # Python's True == 1 (and 1.0 == 1) is not exact JSON return-value truth.
        encode = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return (expected != actual and encode(decode(answer["expected_json"])) == encode(expected)
                and encode(decode(answer["actual_json"])) == encode(actual))
    except (ValueError, TypeError, KeyError):
        return False


def load_tasks():
    document = decode(FIXTURES.read_text())
    tasks = document["tasks"]
    if document["schema_version"] != 1 or len(tasks) != 3 or len({t["id"] for t in tasks}) != len(tasks):
        raise ValueError("invalid_fixtures")
    for task in tasks:
        expected, actual = oracle(task["id"], task["known_counterexample"])
        if expected != task["known_expected"] or actual != task["known_actual"] or expected == actual:
            raise ValueError("invalid_oracle_fixture")
    return tasks


def native(binary, directory, prompt, schema, selection):
    """No tools, MCPs, user/project settings or persisted session. No trust bypass."""
    args = [binary, "-p", "--model", selection["model"], "--setting-sources", "",
        "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--tools", "",
        "--disable-slash-commands", "--no-session-persistence", "--output-format", "json",
        "--json-schema", json.dumps(schema), "--system-prompt",
        "Complete only the synthetic task supplied. Return the requested JSON. No tools, file access, network tools, delegation or task execution."]
    if selection["effort"] is not None:
        args += ["--effort", selection["effort"]]
    args += [prompt]
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env["ROUTER_DISABLE"] = "1"
    start = time.perf_counter_ns()
    try:
        code, output, _, reason, _ = _capture(args, 90, 2_097_152, cwd=directory, env=env)
        elapsed = (time.perf_counter_ns()-start)/1_000_000
        if reason:
            return {"status": reason, "elapsed_ms": elapsed}
        if code:
            raise ValueError()
        result = decode(output)
        if result.get("type") != "result" or result.get("is_error") is not False:
            raise ValueError()
        answer = result.get("structured_output")
        if not isinstance(answer, dict):
            raise ValueError()
        usage = result.get("usage", {})
        counts = {k: usage[k] for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
            "cache_creation_input_tokens") if type(usage.get(k)) is int and usage[k] >= 0}
        model_usage = result.get("modelUsage", {})
        observed = sorted(k for k in model_usage if isinstance(k, str) and
            k.startswith(("claude-haiku-", "claude-sonnet-", "claude-opus-", "claude-fable-")))
        return {"status": "completed", "elapsed_ms": elapsed, "answer": answer,
            "observed_models": observed, "observed_effort": None, "usage": counts}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "elapsed_ms": (time.perf_counter_ns()-start)/1_000_000}
    except OSError:
        return {"status": "native_launch_or_io_failure", "elapsed_ms": (time.perf_counter_ns()-start)/1_000_000}
    except (ValueError, TypeError, KeyError):
        return {"status": "invalid_native_result", "elapsed_ms": (time.perf_counter_ns()-start)/1_000_000}


def trial(task, arm, repeat, binary, key, *, strategy_only=False):
    started = time.perf_counter_ns()
    selection, selection_result, provider_calls, jev_ms = dict(BASELINE), {}, 0, None
    with tempfile.TemporaryDirectory(prefix="router-outcome-task-") as directory:
        if arm == "original_heuristic":
            klass, _ = classify_heuristic(task["description"], DEFAULTS)
            target = target_for_class(klass, DEFAULTS) if klass is not None else None
            if target is not None:
                selection = {"model": target.model, "effort": target.effort}
            selection_result = {"class": klass, "fallback": target is None,
                "scope": "original_heuristic_only_cli_tiebreak_disabled"}
        elif arm == "jev_policy":
            profile = bootstrap_profile("claude", "cli", "2.1.303")
            config = merge_config_layers({"mode": "warn", "consent": {"synthetic_tasks": True}}, {})
            client = JevClient(api_key=key)
            def classify(description):
                nonlocal provider_calls, jev_ms
                if description.text != task["description"]:
                    raise ValueError("unexpected_payload")
                provider_calls += 1
                begin = time.perf_counter_ns()
                result = client.classify(description)
                jev_ms = (time.perf_counter_ns()-begin)/1_000_000
                return result
            decision = assess(TaskEnvelope("claude", EventKind.PREFLIGHT, "pilot", "pilot-task", task["description"], False),
                classify, profile.catalog, config, PolicyScope("cli", "2.1.303", "Agent"),
                synthetic_tasks=frozenset({task["description"]}))
            if decision.recommended_model is not None and decision.recommended_effort is not None:
                selection = {"model": decision.recommended_model, "effort": decision.recommended_effort}
            selection_result = {"reason_code": decision.reason_code,
                "recommended_model": decision.recommended_model, "recommended_effort": decision.recommended_effort,
                "fallback": decision.recommended_model is None, "confidence": decision.confidence}
        elif arm == "parent_selection":
            # This is an actual separate parent recommendation, not a hand label
            # and not proof of selection through a native child spawn.
            selection_result = native(binary, directory,
                "Select a worker for this synthetic task from the schema's measured candidate catalog. "
                "Choose the least demanding candidate likely to solve it correctly. Do not solve the task.\n"+task["description"],
                SELECTION_SCHEMA, BASELINE)
            answer = selection_result.get("answer", {})
            if answer.get("model") in ("haiku", "sonnet") and answer.get("effort") == "medium":
                selection = {"model": answer["model"], "effort": answer["effort"]}
            selection_result["fallback"] = selection == BASELINE and answer != BASELINE
        elif arm != "no_router_parent_baseline":
            raise ValueError("unknown_arm")
        selection_ms = (time.perf_counter_ns()-started)/1_000_000
        if strategy_only:
            return {"requested": selection, "selection": selection_result, "selection_ms": selection_ms,
                    "jev_callback_attempts": provider_calls, "jev_ms": jev_ms}
        # All execution arms receive byte-identical prompts/schema. Answers and
        # grading labels from earlier trials are never supplied to later models.
        prompt = (task["description"]+"\nContract: "+task["contract"]+"\nNumbered source:\n"+task["source"]+
            "\nReturn the incorrect line and a concrete counterexample. Values must be at most32 integers in[-100,100]; "
            "target must be null except for binary search. expected_json/actual_json are JSON-encoded return values. "
            "Do not repair or execute code; reason from the source.")
        execution = native(binary, directory, prompt, ANSWER_SCHEMA, selection)
    return {"task_id": task["id"], "arm": arm, "repeat": repeat,
        "requested": selection, "selection": selection_result, "selection_ms": selection_ms,
        "jev_callback_attempts": provider_calls, "jev_ms": jev_ms, "execution": execution,
        "oracle_success": grade(task, execution.get("answer")),
        "total_ms": (time.perf_counter_ns()-started)/1_000_000,
        "orchestrator_execution_attempts": 1, "orchestrator_retries": 0,
        "native_or_provider_internal_retries": "not_observed", "human_rework": None}


def clustered_interval(rows, arm, seed=731):
    """Task-cluster bootstrap; descriptive only with three clusters."""
    ids = sorted({r["task_id"] for r in rows})
    means = [sum(r["oracle_success"] for r in rows if r["arm"] == arm and r["task_id"] == task_id)/
        sum(r["arm"] == arm and r["task_id"] == task_id for r in rows) for task_id in ids]
    rng = random.Random(seed)
    draws = sorted(sum(rng.choice(means) for _ in means)/len(means) for _ in range(2000))
    return {"method": "descriptive_empirical_task_cluster_bootstrap", "clusters": len(ids), "resamples": 2000,
            "lower": draws[49], "upper": draws[1949],
            "warning": "not_calibrated_success_CI; three_purposive_clusters; all_success_range_degenerates; no_reliability_or_noninferiority_inference"}


def summarize(rows):
    """All failures remain in denominators; usage is only host-observed proxy."""
    summaries = {}
    for arm in ARMS:
        selected = [r for r in rows if r["arm"] == arm]
        calls = [r["execution"] for r in selected]
        if arm == "parent_selection":
            calls += [r["selection"] for r in selected]
        usage = {}
        for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            observed = [c["usage"][key] for c in calls if type(c.get("usage", {}).get(key)) is int]
            usage[key] = {"observed_sum": sum(observed), "calls_with_counter": len(observed),
                          "calls_missing_counter": len(calls)-len(observed)}
        times = sorted(r["total_ms"] for r in selected)
        summaries[arm] = {"attempts": len(selected),
            "oracle_successes": sum(r["oracle_success"] for r in selected),
            "descriptive_empirical_success_range": clustered_interval(rows, arm),
            "total_wall_ms": {"p50": times[(len(times)-1)//2], "p95": times[-1]},
            "jev_callback_attempts": sum(r["jev_callback_attempts"] for r in selected),
            "native_call_results": len(calls), "usage_counters_not_quota": usage,
            "human_rework": None}
    return summaries


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-synthetic", action="store_true")
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--binary", default="/opt/homebrew/bin/claude")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.run_synthetic or args.key_file is None:
        parser.error("explicit --run-synthetic and --key-file required")
    if subprocess.check_output([args.binary, "--version"], text=True).strip().split()[0] != "2.1.303":
        parser.error("unmeasured host version")
    tasks = load_tasks()
    key = load_private_key(args.key_file)
    result = {"schema_version": 1, "status": "running", "recorded_at": datetime.now(timezone.utc).isoformat(),
        "scope": "synthetic_code_review_direct_executor_pilot_not_native_worker_integration",
        "fixture_sha256": hashlib.sha256(FIXTURES.read_bytes()).hexdigest(),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runtime": "claude", "host_version": "2.1.303", "parent_baseline": BASELINE,
        "arms": list(ARMS), "repeats": 2, "rows": [],
        "not_measured": ["accepted_code_changes/test_quality", "human_correction/rework", "native_child_inheritance",
            "automatic_hook_routing", "Codex", "desktop", "representative_engineering_quality", "subscription_cost/savings"],
        "provenance": "self_authored_synthetic_public_task_payloads_only"}
    jobs = [(task, arm, repeat) for repeat in range(2) for task in tasks for arm in ARMS]
    random.Random(731).shuffle(jobs)
    def checkpoint():
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    checkpoint()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(trial, task, arm, repeat, args.binary, key) for task, arm, repeat in jobs]
        for future in as_completed(futures):
            result["rows"].append(future.result())
            checkpoint()
            print(json.dumps({"completed": len(result["rows"]), "total": len(jobs)}), flush=True)
    result["summary"] = summarize(result["rows"])
    result["status"] = "pilot_measured_not_release_validation"
    checkpoint()
    return 0


if __name__ == "__main__":
    sys.exit(main())

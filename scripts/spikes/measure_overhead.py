#!/usr/bin/env python3
"""Reproducible synthetic core overhead probe, not a host/task benchmark.

Offline by default. --live-synthetic sends ONLY the shipped SYNTHETIC_SMOKE
description through the production JevClient. Never reads project content or
principal runtime configuration; no installation, host run or worker mutation.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import sys
import tempfile
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from router_core.classifier import JevClient
from router_core.catalog import CapabilityRecord, CatalogRegistry
from router_core.config import merge_config_layers
from router_core.contracts import ProviderResult, ProviderStatus, TaskRequirements
from router_core.credentials import load_private_key
from router_core.native import NativeAdapter, bootstrap_profile
from router_core.privacy import SYNTHETIC_SMOKE
from router_core.state import PrivateStateStore, StateScope

CONTINUATIONS = ("sim", "continue", "also add tests", "what about that output?")
VERSIONS = {"claude": "2.1.303", "codex": "0.163.0"}


def distribution(values):
    """Nearest-rank percentiles; empty groups are null, never zero latency."""
    ordered = sorted(values)
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in ordered):
        raise ValueError("invalid_timing")
    if not ordered:
        return {"n": 0, "p50_ms": None, "p95_ms": None}
    return {"n": len(ordered), "p50_ms": ordered[math.ceil(.5*len(ordered))-1],
            "p95_ms": ordered[math.ceil(.95*len(ordered))-1], "min_ms": ordered[0], "max_ms": ordered[-1]}


def sequence(adapter, runtime, session, *, call_count, fixture_model=False):
    """One new root task, duplicate delivery, four follow-ups and a tool loop."""
    model = "claude-haiku-5-5" if runtime == "claude" else "gpt-6-luna"
    if fixture_model:
        model = "fixture-haiku" if runtime == "claude" else "fixture-luna"
    base = {"cwd": adapter.project_id, "session_id": session, "model": model, "effort": "medium"}
    prompt = {**base, "hook_event_name": "UserPromptSubmit", "prompt": SYNTHETIC_SMOKE,
              "turn_id": "initial", "prompt_id": "initial"}
    events = [("session_start", {**base, "hook_event_name": "SessionStart", "source": "startup"}),
              ("new_task", prompt), ("duplicate", prompt)]
    events += [("continuation", {**prompt, "prompt": text, "turn_id": f"followup-{i}",
                                 "prompt_id": f"followup-{i}"}) for i, text in enumerate(CONTINUATIONS)]
    events += [("unrelated_tool", {**base, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                                   "tool_use_id": "unrelated", "tool_input": {"command": "true"}}),
               ("stop", {**base, "hook_event_name": "Stop"})]
    timings, warnings = [], Counter()
    # Measure the full public handler, including snapshots, boundary/state and
    # telemetry append. Telemetry's assessment.elapsed_ms alone excludes these.
    for phase, event in events:
        original = json.dumps(event, sort_keys=True)
        calls_before = call_count()
        started = time.perf_counter_ns()
        output = adapter.handle(event)
        duration = (time.perf_counter_ns()-started)/1_000_000
        if json.dumps(event, sort_keys=True) != original:
            raise ValueError("input_mutated")
        if output is not None:
            if (phase != "new_task" or "updatedInput" in output.get("hookSpecificOutput", {})
                    or "permissionDecision" in output.get("hookSpecificOutput", {})):
                raise ValueError("unexpected_native_output")
            warnings[phase] += 1
        calls = call_count()-calls_before
        if phase != "new_task" and calls:
            raise ValueError("classification_outside_new_task")
        timings.append({"phase": phase, "elapsed_ms": duration, "callback_attempts": calls})
    if adapter.config.mode != "disabled":
        actual = adapter.store.get_root(StateScope(runtime, adapter.project_id, session))
        if actual != {"model": base["model"], "effort": "medium"}:
            raise ValueError("root_observation_changed")
    return {"timings": timings, "total_ms": sum(t["elapsed_ms"] for t in timings),
            "warnings": sum(warnings.values())}


def local_measurements(directory, repeats):
    """Alternate paired arms; retain growing logs/state instead of resetting."""
    arms, samples = {}, []
    for runtime in VERSIONS:
        profile = bootstrap_profile(runtime, "cli", VERSIONS[runtime])
        # Synthetic catalog only for a controlled warning-positive path. These
        # fixture IDs never reach a runtime or become production capabilities.
        targets = (("haiku", "5.5"), ("sonnet", "5.5")) if runtime == "claude" else (("luna", "6"), ("sol", "6.1"))
        tool = next(iter(profile.spawn.tools))
        profile = replace(profile, catalog=CatalogRegistry(tuple(CapabilityRecord(
            runtime, "cli", VERSIONS[runtime], family, version, "fixture-"+family, tool,
            "model", "effort" if runtime == "claude" else "reasoning_effort", ("low", "medium", "high"),
            "verified", "Synthetic measurement fixture, not runtime evidence", "test_fixture",
            "2026-10-19T00:00:00Z") for family, version in targets)))
        for mode in ("disabled", "shadow", "warn"):
            for logging in (False, True):
                label = f"{runtime}:{mode}:log={logging}"
                config = merge_config_layers({"mode": mode, "consent": {"synthetic_tasks": True},
                    "observability": {"log_decisions": logging}}, {})
                counter = Counter()
                def classify(description, counter=counter):
                    if description.provider_state() != {"task_summary": SYNTHETIC_SMOKE}:
                        raise ValueError("unexpected_payload")
                    counter["calls"] += 1
                    # Deliberately deterministic fixture to measure bookkeeping,
                    # not classifier accuracy or real service/model latency.
                    return ProviderResult(ProviderStatus.SUCCESS,
                        TaskRequirements(.1, .1, .1, .99, "T1", risk="low"))
                store = PrivateStateStore(directory/label)
                arms[label] = (NativeAdapter(profile, config, store, classify,
                    project_id=str(directory)), counter)
    for index in range(repeats):
        labels = list(arms)
        if index % 2:
            labels.reverse()
        for label in labels:
            adapter, counter = arms[label]
            before = counter["calls"]
            sample = sequence(adapter, adapter.profile.spawn.runtime.value, f"task-{index}",
                call_count=lambda: counter["calls"], fixture_model=True)
            sample.update(arm=label, replicate=index, callback_attempts=counter["calls"]-before)
            enabled = adapter.config.mode != "disabled"
            if sample["callback_attempts"] != int(enabled):
                raise ValueError("call_count_mismatch")
            if sample["warnings"] != int(adapter.config.mode == "warn"):
                raise ValueError("warning_count_mismatch")
            samples.append(sample)
    summaries = {}
    for label, (adapter, counter) in arms.items():
        rows = [s for s in samples if s["arm"] == label]
        phases = defaultdict(list)
        for sample in rows:
            for timing in sample["timings"]:
                phases[timing["phase"]].append(timing["elapsed_ms"])
        logged = adapter.config.mode != "disabled" and adapter.config.observability.log_decisions
        retained = len(adapter.telemetry.read()) if logged else 0
        files = [directory/label/name for name in adapter.telemetry.NAMES]
        sizes = [p.stat().st_size if p.exists() else 0 for p in files]
        summaries[label] = {"sequence_latency": distribution([s["total_ms"] for s in rows]),
            "by_phase": {p: distribution(t) for p, t in phases.items()},
            "callback_attempts": counter["calls"], "new_tasks": repeats,
            "calls_per_new_task": counter["calls"]/repeats,
            "warning_count": sum(s["warnings"] for s in rows),
            "warnings_per_new_task": sum(s["warnings"] for s in rows)/repeats,
            "continuation_events": len(CONTINUATIONS)*repeats,
            "continuation_callback_attempts": sum(t["callback_attempts"] for s in rows for t in s["timings"] if t["phase"] == "continuation"),
            "duplicate_callback_attempts": sum(t["callback_attempts"] for s in rows for t in s["timings"] if t["phase"] == "duplicate"),
            "retained_telemetry_rows": retained, "telemetry_file_bytes": sizes}
        if logged and not retained:
            raise ValueError("telemetry_missing")
        if adapter.config.mode == "disabled" and (directory/label).exists():
            raise ValueError("disabled_wrote_state")
    differences = {}
    lookup = {(s["arm"], s["replicate"]): s["total_ms"] for s in samples}
    for runtime in VERSIONS:
        for mode in ("disabled", "shadow", "warn"):
            differences[f"{runtime}:{mode}:logging_on_minus_off"] = distribution([
                lookup[(f"{runtime}:{mode}:log=True", i)]-lookup[(f"{runtime}:{mode}:log=False", i)]
                for i in range(repeats)])
        for logging in (False, True):
            for mode in ("shadow", "warn"):
                differences[f"{runtime}:{mode}_minus_disabled:log={logging}"] = distribution([
                    lookup[(f"{runtime}:{mode}:log={logging}", i)]-
                    lookup[(f"{runtime}:disabled:log={logging}", i)] for i in range(repeats)])
    return {"summaries": summaries, "paired_sequence_deltas": differences, "samples": samples,
            "external_calls": 0, "classifier": "deterministic_injected_T1_not_service_latency",
            "catalog": "synthetic_fixture_models_not_runtime_capability_evidence"}


def live_measurements(directory, count, key_file):
    # Resolve credentials only on explicit opt-in. No task/path/config fields
    # come from the project; each outbound description is the shipped fixture.
    client = JevClient(api_key=load_private_key(key_file))
    attempts, rows = [], []
    for index in range(count):
        runtime = tuple(VERSIONS)[index % 2]
        calls = []
        def classify(description):
            if description.provider_state() != {"task_summary": SYNTHETIC_SMOKE}:
                raise ValueError("unexpected_live_payload")
            start = time.perf_counter_ns()
            result = client.classify(description)
            calls.append({"elapsed_ms": (time.perf_counter_ns()-start)/1_000_000,
                "status": result.status.value, "reason_code": result.reason_code})
            return result
        config = merge_config_layers({"mode": "warn", "consent": {"synthetic_tasks": True}}, {})
        adapter = NativeAdapter(bootstrap_profile(runtime, "cli", VERSIONS[runtime]), config,
            PrivateStateStore(directory/f"live-{runtime}"), classify, project_id=str(directory))
        row = sequence(adapter, runtime, f"live-{index}", call_count=lambda: len(calls))
        if len(calls) != 1:
            raise ValueError("live_call_count_mismatch")
        row.update(runtime=runtime, replicate=index, callback_attempts=len(calls), provider=calls[0])
        attempts.extend(calls); rows.append(row)
    statuses = Counter(r["status"] for r in attempts)
    try:
        sdk_version = importlib.metadata.version("typesafe-sdk")
    except importlib.metadata.PackageNotFoundError:
        sdk_version = "unavailable"
    return {"callback_attempts": len(attempts), "client_results": dict(statuses), "sdk_version": sdk_version,
        "client_wall_latency_all_results": distribution([r["elapsed_ms"] for r in attempts]),
        "client_wall_latency_success_only": distribution([r["elapsed_ms"] for r in attempts if r["status"] == "success"]),
        "new_root_handler_latency": distribution([t["elapsed_ms"] for s in rows for t in s["timings"] if t["phase"] == "new_task"]),
        "warning_count": sum(s["warnings"] for s in rows), "samples": rows,
        "wire_request_count": "not_observed_sdk_internal_transport",
        "client_wall_scope": "production_JevClient_cold_worker_import_and_network_and_normalization; credential_read_excluded",
        "deadline_ms": client.deadline_ms, "new_tasks": count,
        "continuation_events": len(CONTINUATIONS)*count,
        "continuation_callback_attempts": sum(t["callback_attempts"] for s in rows for t in s["timings"] if t["phase"] == "continuation"),
        "duplicate_callback_attempts": sum(t["callback_attempts"] for s in rows for t in s["timings"] if t["phase"] == "duplicate")}


def bounded_count(value):
    if not value.isascii() or not value.isdecimal() or not 2 <= int(value) <= 100:
        raise argparse.ArgumentTypeError("count must be 2..100")
    return int(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=bounded_count, default=30)
    parser.add_argument("--live-synthetic", action="store_true")
    parser.add_argument("--live-samples", type=bounded_count, default=20)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.live_synthetic != (args.key_file is not None):
        parser.error("--live-synthetic and --key-file are required together")
    try:
        with tempfile.TemporaryDirectory(prefix="router-overhead-") as temporary:
            directory = Path(temporary).resolve()
            result = {"schema_version": 1, "recorded_at": datetime.now(timezone.utc).isoformat(),
                "scope": "synthetic_core_handler_not_native_UI_or_task_completion",
                "python": platform.python_version(), "platform": platform.system()+" "+platform.machine(),
                "host_profiles": VERSIONS, "percentile_method": "nearest_rank",
                "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "local": local_measurements(directory, args.repeats),
                "not_measured": ["desktop", "native runtime startup and hook delivery", "human warning UX",
                    "task success/retries", "subscription savings", "wire request count", "cache hit rate",
                    "maximum-capacity telemetry steady state"]}
            if args.live_synthetic:
                result["live"] = live_measurements(directory, args.live_samples, args.key_file)
            result["status"] = "measured"
        rendered = json.dumps(result, indent=2, allow_nan=False)+"\n"
        if args.output:
            args.output.write_text(rendered)
        print(json.dumps({"status": result["status"], "local_arms": len(result["local"]["summaries"]),
            "live_callback_attempts": result.get("live", {}).get("callback_attempts", 0)}))
        return 0
    except Exception:
        print(json.dumps({"status": "error", "reason_code": "overhead_measurement_failed"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())

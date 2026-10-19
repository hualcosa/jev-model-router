from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import fcntl
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from router_core.contracts import ProviderResult, ProviderStatus, TaskRequirements
from router_core.native import bootstrap_profile
from router_core.state import PrivateStateStore, StateScope
from router_core.telemetry import TelemetryError, TelemetryLog, TelemetryRecord, observation_record, activity_record
from tests import test_native_adapter as native_helpers


def _append_process(root, count):
    store = PrivateStateStore(root, lock_wait_seconds=3)
    log = TelemetryLog(store)
    profile = bootstrap_profile("codex", "cli", "0.163.0").spawn
    scope = StateScope("codex", str(Path(root).parent), "session")
    for _ in range(count):
        log.append(observation_record(profile, "shadow", scope,
            {"hook_event_name": "SubagentStop", "agent_id": "agent", "model": "gpt-6-luna"}))


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "state"
        self.store = PrivateStateStore(self.root)
        self.log = TelemetryLog(self.store)
        self.scope = StateScope("codex", self.tmp.name, "PRIVATE_SESSION")
        self.profile = bootstrap_profile("codex", "cli", "0.163.0").spawn

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, **event):
        return observation_record(self.profile, "shadow", self.scope,
            {"hook_event_name": "SubagentStop", "agent_id": "PRIVATE_AGENT", "model": "gpt-6-luna", **event})

    def test_roundtrip_hashed_scoped_ids_and_no_raw_fields(self):
        record = self.record(prompt="PRIVATE_PROMPT", tool_response={"token": "PRIVATE_KEY"},
            transcript_path="PRIVATE_PATH", agent_type="PRIVATE_CUSTOM", effort={"level": "high"})
        raw = record.encoded
        for forbidden in ("PRIVATE_", self.tmp.name, "transcript", "prompt", "agent_type", "high"):
            self.assertNotIn(forbidden, raw)
        data = record.to_dict()
        self.assertIsNone(data["data"]["actual_effort"])
        self.assertEqual(data["data"]["actual_execution"], "reported_by_host")
        self.assertEqual(TelemetryRecord(raw), record)
        other_scope = StateScope("codex", self.tmp.name, "other")
        other = observation_record(self.profile, "shadow", other_scope,
            {"hook_event_name": "SubagentStop", "agent_id": "PRIVATE_AGENT"})
        self.assertNotEqual(other.to_dict()["agent_hash"], data["agent_hash"])
        self.assertNotIn("PRIVATE_", repr(record))

    def test_arguments_never_become_actual(self):
        r = self.record(hook_event_name="PostToolUse", agent_id=None,
            tool_name="collaborationspawn_agent", tool_use_id="PRIVATE_CALL",
            tool_input={"model": "gpt-6.1-sol", "reasoning_effort": "high", "message": "PRIVATE_TEXT"},
            tool_response={"model": "gpt-6-astra", "agent_id": "PRIVATE_AGENT"}, model="gpt-6-astra")
        d = r.to_dict()
        self.assertEqual(d["data"]["argument_model"], "gpt-6.1-sol")
        self.assertEqual(d["data"]["argument_effort"], "high")
        self.assertIsNone(d["data"]["actual_model"])
        self.assertIsNone(d["agent_hash"])
        self.assertEqual(d["data"]["actual_execution"], "unverified")
        self.assertEqual(d["data"]["correlation"], "unverified")

    def test_claude_only_reports_stop_effort_not_child_model(self):
        self.profile = bootstrap_profile("claude", "cli", "2.1.303").spawn
        self.scope = StateScope("claude", self.tmp.name, "session")
        d = self.record(model="claude-opus-5-5", effort={"level": "high"}).to_dict()["data"]
        self.assertIsNone(d["actual_model"])
        self.assertEqual(d["actual_effort"], "high")
        self.assertEqual(d["actual_execution"], "reported_by_host")
        for source, effort in (("SubagentStart", {"level": "high"}), ("SubagentStop", "high"),
                               ("SubagentStop", {"level": "ultra"})):
            d = self.record(hook_event_name=source, effort=effort).to_dict()["data"]
            self.assertIsNone(d["actual_effort"])
            self.assertEqual(d["actual_execution"], "unverified")

    def test_root_observation_does_not_infer_effort(self):
        for source in ("SessionStart", "UserPromptSubmit"):
            d = self.record(hook_event_name=source, agent_id=None, effort="high").to_dict()["data"]
            self.assertEqual(d["actual_model"], "gpt-6-luna")
            self.assertIsNone(d["actual_effort"])
        self.profile = bootstrap_profile("claude", "cli", "2.1.303").spawn
        self.scope = StateScope("claude", self.tmp.name, "session")
        d = self.record(hook_event_name="PostModelSwitch", agent_id=None,
            to_model="claude-sonnet-5-5", requested_model="PRIVATE_PIN", effort={"level": "max"}).to_dict()["data"]
        self.assertEqual(d["actual_model"], "claude-sonnet-5-5")
        self.assertIsNone(d["actual_effort"])

    def test_unknown_fields_labels_and_hosts_not_passed_through(self):
        for bad in ("SECRET_KEY", "gpt-6-luna\nPRIVATE", "gpt-6-luna$(evil)", {}, [], 5, "a"*100000):
            r = self.record(model=bad)
            self.assertIsNone(r.to_dict()["data"]["actual_model"])
        for event in ({"hook_event_name": "Unknown"}, {"hook_event_name": "UserPromptSubmit", "agent_id": "child"},
                      {"agent_id": None}, {"hook_event_name": "PostModelSwitch", "agent_id": None},
                      {"hook_event_name": "PostToolUse", "agent_id": None, "tool_name": "Bash"}):
            self.assertIsNone(self.record(**event))
        for change in ({"surface": "desktop"}, {"host_version": "0.164.0"}):
            self.profile = replace(self.profile, **change)
            self.assertIsNone(self.record())

    def test_strict_reader_rejects_untrusted_record_values(self):
        base = self.record().to_dict()
        for patch in ({"prompt": "PRIVATE"}, {"timestamp": float("nan")}, {"timestamp": 10**400}, {"schema": True},
                      {"scope_hash": "PRIVATE"}, {"host_version": "unknown"}):
            with self.subTest(patch=patch), self.assertRaises(TelemetryError):
                TelemetryRecord(json.dumps({**base, **patch}))
        for patch in ({"actual_execution": "verified"}, {"actual_effort": "high"},
                      {"correlation": "verified"}, {"actual_model": "PRIVATE"}, {"argument_model": "gpt-6-luna"}):
            with self.subTest(patch=patch), self.assertRaises(TelemetryError):
                TelemetryRecord(json.dumps({**base, "data": {**base["data"], **patch}}))
        with self.assertRaises(TelemetryError):
            TelemetryRecord(self.record().encoded.replace('"schema":1', '"schema":1,"schema":1'))

    def test_activity_strict_enums_hash_ids_and_unknown_reason_sanitized(self):
        r = activity_record(self.profile, "shadow", self.scope, "spawn", "pinned", "PRIVATE_PIN",
                            task_id="PRIVATE_TASK", tool_id="PRIVATE_TOOL")
        self.assertEqual(r.to_dict()["data"], {"phase": "pinned", "reason": "unclassified_reason"})
        self.assertNotIn("PRIVATE", r.encoded)
        d = r.to_dict()
        for data in ({"phase": "PRIVATE", "reason": "explicit_pin"},
                     {"phase": "pinned", "reason": "PRIVATE"},
                     {"phase": "pinned", "reason": "explicit_pin", "actual_model": "gpt-6-luna"}):
            with self.assertRaises(TelemetryError):
                TelemetryRecord(json.dumps({**d, "data": data}))

    def test_log_constructor_and_empty_reader_no_files_created(self):
        self.assertEqual(self.log.read(), [])
        self.assertFalse(self.root.exists())
        self.root.mkdir(mode=0o700)
        self.assertEqual(self.log.read(), [])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_append_private_atomic_roundtrip_and_read_only(self):
        r = self.record()
        self.log.append(r)
        before = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in self.root.iterdir()}
        self.assertEqual(self.log.read(), [r])
        after = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in self.root.iterdir()}
        self.assertEqual(before, after)
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        for p in self.root.iterdir():
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("state.json", before)

    def test_rotation_bounded_and_complete_jsonl(self):
        self.log = TelemetryLog(self.store, max_bytes=8192)
        sent = []
        for _ in range(50):
            r = self.record()
            self.log.append(r)
            sent.append(r)
        rows = self.log.read()
        self.assertGreater(len(rows), 1)
        self.assertLess(len(rows), len(sent))
        self.assertEqual(rows[-1], sent[-1])
        self.assertEqual(len({r.to_dict()["row_id"] for r in rows}), len(rows))
        for p in self.root.glob("telemetry*"):
            self.assertLessEqual(p.stat().st_size, 8192)
            self.assertTrue(p.read_bytes().endswith(b"\n"))
        self.assertFalse(list(self.root.glob(".tmp-*")))

    def test_concurrent_writers_and_reader_no_torn_rows(self):
        sent = [self.record() for _ in range(40)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(self.log.append, record) for record in sent]
            for _ in range(10):
                self.log.read()
            for future in futures:
                future.result()
        self.assertEqual({r.encoded for r in self.log.read()}, {r.encoded for r in sent})

    def test_symlink_hardlink_fifo_and_public_file_rejected_without_mutation(self):
        for kind in ("symlink", "hardlink", "fifo", "public"):
            with self.subTest(kind=kind):
                self.log.append(self.record())
                path = self.root / "telemetry.1.jsonl"
                outside = Path(self.tmp.name) / "secret"
                outside.write_text("PRIVATE_KEY")
                outside.chmod(0o600)
                if kind == "symlink":
                    path.symlink_to(outside)
                elif kind == "hardlink":
                    os.link(outside, path)
                elif kind == "fifo":
                    os.mkfifo(path, 0o600)
                else:
                    path.write_text("")
                    path.chmod(0o644)
                before = (self.root / "telemetry.jsonl").read_bytes()
                with self.assertRaises(TelemetryError):
                    self.log.append(self.record())
                with self.assertRaises(TelemetryError):
                    self.log.read()
                self.assertEqual((self.root / "telemetry.jsonl").read_bytes(), before)
                self.assertEqual(outside.read_text(), "PRIVATE_KEY")
                path.unlink()
                outside.unlink()

    def test_invalid_torn_json_and_missing_lock_fail_closed(self):
        self.log.append(self.record())
        p = self.root / "telemetry.jsonl"
        for content in (b"PRIVATE_KEY", b'{"unexpected":"PRIVATE_KEY"}\n', b"\n"):
            p.write_bytes(content)
            with self.assertRaises(TelemetryError):
                self.log.append(self.record())
            self.assertEqual(p.read_bytes(), content)
            with self.assertRaises(TelemetryError):
                self.log.read()
        (self.root / "state.lock").unlink()
        with self.assertRaises(TelemetryError):
            self.log.read()
        self.assertFalse((self.root / "state.lock").exists())

    def test_rotation_interruption_does_not_duplicate_reader_rows(self):
        self.log.append(self.record())
        current = self.root / "telemetry.jsonl"
        archive = self.root / "telemetry.1.jsonl"
        archive.write_bytes(current.read_bytes())
        archive.chmod(0o600)
        self.assertEqual(len(self.log.read()), 1)

    def test_separate_process_first_use_writers(self):
        ctx = multiprocessing.get_context("spawn")
        workers = [ctx.Process(target=_append_process, args=(str(self.root), 8)) for _ in range(3)]
        for worker in workers:
            worker.start()
        try:
            for worker in workers:
                worker.join(timeout=10)
                self.assertFalse(worker.is_alive())
                self.assertEqual(worker.exitcode, 0)
            self.assertEqual(len(self.log.read()), 24)
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=3)

    def test_failed_atomic_publish_keeps_current_and_cleans_temp(self):
        first = self.record()
        self.log.append(first)
        with patch("router_core.telemetry.os.replace", side_effect=OSError("PRIVATE_ERROR")):
            with self.assertRaises(TelemetryError) as error:
                self.log.append(self.record())
        self.assertEqual(str(error.exception), "telemetry_unavailable")
        self.assertEqual(self.log.read(), [first])
        self.assertFalse(list(self.root.glob(".tmp-*")))

    def test_lock_timeout_is_bounded_read_only_and_sanitized(self):
        self.log.append(self.record())
        fd = os.open(self.root / "state.lock", os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.store.lock_wait_seconds = 0
            with self.assertRaises(TelemetryError):
                self.log.read()
            with self.assertRaises(TelemetryError):
                self.log.append(self.record())
        finally:
            os.close(fd)
        self.assertEqual(len(self.log.read()), 1)

    def test_public_root_rejected_not_repaired(self):
        self.root.mkdir(mode=0o755)
        self.root.chmod(0o755)
        with self.assertRaises(TelemetryError):
            self.log.append(self.record())
        with self.assertRaises(TelemetryError):
            self.log.read()
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o755)


class NativeTelemetryTests(unittest.TestCase):
    setUp = native_helpers.NativeAdapterTests.setUp
    tearDown = native_helpers.NativeAdapterTests.tearDown
    adapter = native_helpers.NativeAdapterTests.adapter
    event = native_helpers.NativeAdapterTests.event
    classifier = native_helpers.NativeAdapterTests.classifier
    def test_assessment_records_normalized_only_and_cached_no_recall(self):
        adapter = self.adapter(mode="shadow")
        def classifier(payload):
            self.calls.append(payload)
            return ProviderResult(ProviderStatus.SUCCESS,
                TaskRequirements(.1, .2, .3, .99, "T0", risk="low", provider_raw_tier="PRIVATE_RAW"),
                provider="PRIVATE_PROVIDER", reason_code="PRIVATE_PROSE")
        adapter.classify = classifier
        for _ in range(2):
            self.assertIsNone(adapter.handle(self.event()))
        self.assertEqual(len(self.calls), 1)
        all_rows = adapter.telemetry.read()
        rows = [r for r in all_rows if r.to_dict()["source"] == "assessment"]
        self.assertEqual(len(rows), 1)
        self.assertTrue(any(r.to_dict()["data"].get("phase") == "cached" for r in all_rows))
        self.assertFalse(any(r.to_dict()["data"].get("phase") == "emitted" for r in all_rows))
        d = rows[0].to_dict()["data"]
        self.assertEqual(d["reason"], "shadow_mode")
        self.assertEqual(d["provider_calls"], 1)
        self.assertEqual(d["requirements"]["tier"], "T0")
        self.assertIsNotNone(d["recommended_model"])
        self.assertNotIn("PRIVATE", rows[0].encoded)
        self.assertNotIn("prompt", rows[0].encoded)

    def test_pins_custom_and_permission_fallback_logged_without_classification(self):
        adapter = self.adapter()
        for args in ({"model": "PRIVATE_PIN"}, {"subagent_type": "PRIVATE_CUSTOM"}):
            self.assertIsNone(adapter.handle(self.event(tool_input={"prompt": "PRIVATE_TASK", **args})))
        self.assertIsNone(adapter.handle(self.event(permission_mode="plan")))
        self.assertEqual(self.calls, [])
        rows = adapter.telemetry.read()
        self.assertEqual({r.to_dict()["data"]["phase"] for r in rows}, {"pinned", "custom_profile", "unchanged"})
        self.assertNotIn("PRIVATE", "".join(r.encoded for r in rows))
        self.assertFalse(any(r.to_dict()["source"] == "assessment" for r in rows))

    def test_provider_exception_logged_failure_no_retry_and_no_exception_text(self):
        adapter = self.adapter(mode="shadow")
        def failed(payload):
            self.calls.append(payload)
            raise RuntimeError("PRIVATE_FAILURE")
        adapter.classify = failed
        self.assertIsNone(adapter.handle(self.event()))
        self.assertIsNone(adapter.handle(self.event()))
        self.assertEqual(len(self.calls), 1)
        rows = [r for r in adapter.telemetry.read() if r.to_dict()["source"] == "assessment"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].to_dict()["data"]["provider_status"], "failure")
        self.assertIsNone(rows[0].to_dict()["data"]["requirements"])
        self.assertNotIn("PRIVATE", rows[0].encoded)

    def test_unknown_boundary_logs_reason_without_root_classification(self):
        adapter = self.adapter(mode="shadow")
        adapter.handle(self.event(hook_event_name="SessionStart", model="haiku"))
        self.assertIsNone(adapter.handle(self.event(hook_event_name="UserPromptSubmit", prompt="hmm")))
        self.assertEqual(self.calls, [])
        rows = [r for r in adapter.telemetry.read() if r.to_dict()["source"] == "boundary"]
        self.assertEqual(rows[-1].to_dict()["data"]["phase"], "unknown")
        self.assertNotIn("hmm", rows[-1].encoded)

    def test_logging_off_has_no_telemetry_io(self):
        adapter = self.adapter(observability={"log_decisions": False})
        with patch.object(adapter.telemetry, "append", side_effect=AssertionError("must not log")) as append:
            self.assertIsNotNone(adapter.handle(self.event()))
            append.assert_not_called()
        self.assertFalse(list(Path(self.project).rglob("telemetry*")))

    def test_disabled_no_state_or_telemetry_io(self):
        adapter = self.adapter(mode="disabled")
        self.assertIsNone(adapter.handle(self.event(hook_event_name="SessionStart", model="haiku")))
        self.assertIsNone(adapter.handle(self.event()))
        self.assertFalse(self.store.root.exists())
        self.assertEqual(self.calls, [])

    def test_log_failure_does_not_affect_output_or_provider_count(self):
        adapter = self.adapter()
        with patch.object(adapter.telemetry, "append", side_effect=OSError("PRIVATE_FAILURE")):
            first = adapter.handle(self.event())
            second = adapter.handle(self.event())
        self.assertIsNotNone(first)
        self.assertEqual(first, second)
        self.assertEqual(len(self.calls), 1)

    def test_child_observation_never_overwrites_root_or_classifies(self):
        adapter = self.adapter("codex", mode="shadow")
        event = self.event("codex", hook_event_name="SessionStart", model="gpt-6-luna")
        adapter.handle(event)
        scope = StateScope("codex", self.project, "session")
        before = self.store.get_root(scope)
        adapter.handle({**event, "hook_event_name": "SubagentStop", "agent_id": "child", "model": "gpt-6.1-sol", "reasoning_effort": "high"})
        self.assertEqual(self.store.get_root(scope), before)
        self.assertEqual(self.calls, [])
        rows = adapter.telemetry.read()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1].to_dict()["data"]["actual_model"], "gpt-6.1-sol")
        self.assertIsNone(rows[-1].to_dict()["data"]["actual_effort"])


if __name__ == "__main__":
    unittest.main()

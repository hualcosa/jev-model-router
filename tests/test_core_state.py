"""Offline POSIX state, crash, privacy and independent-process stress tests."""
import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import stat
import tempfile
import time
import unittest
from unittest import mock

from router_core.boundary import BoundaryEvent, BoundaryClass, Lifecycle
from router_core.contracts import RouteDecision
from router_core.state import PrivateStateStore, StateScope, StateError, StateDisposition


def decision(model="fixture-luna"):
    return RouteDecision("route_worker", "eligible", "1.0.0", "subagent_spawn",
                         selected_model=model, selected_effort="medium", provenance="policy_prior")


def _run_worker(root, scope, key, counter, ready, output, model="fixture-luna"):
    ready.wait(10)
    def callback():
        with counter.get_lock():
            counter.value += 1
        time.sleep(0.05)
        return decision(model)
    result = PrivateStateStore(root, lock_wait_seconds=3).run_once(scope, key, callback)
    status = result.disposition.value
    if result.error is not None:
        cause = result.error.__context__
        frames = []
        traceback = cause.__traceback__ if cause is not None else None
        while traceback is not None:
            frames.append(traceback.tb_frame.f_code.co_name + ":" + str(traceback.tb_lineno))
            traceback = traceback.tb_next
        # Test diagnostics only: errno/type/function names, never path/message.
        status = "error:" + result.error.code + ":" + type(cause).__name__ + ":" + str(getattr(cause, "errno", None)) + ":" + "/".join(frames)
    output.put((status, result.decision.selected_model if result.decision else None))


def _consume_worker(root, scope, reference, ready, output):
    ready.wait(10)
    result = PrivateStateStore(root, lock_wait_seconds=3).consume_prepared(scope, reference)
    output.put(result.selected_model if result else None)


def _crash_worker(root, scope):
    PrivateStateStore(root).run_once(scope, "crashed-event", lambda: os._exit(17))


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "private"
        self.scope = StateScope("codex", "secret-project-path", "secret-session-id")
        self.store = PrivateStateStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_computed_cached_typed_and_private(self):
        result = self.store.run_once(self.scope, "secret-call-id", decision)
        self.assertEqual(result.disposition, StateDisposition.COMPUTED)
        cached = PrivateStateStore(self.root).run_once(self.scope, "secret-call-id", lambda: self.fail("second callback"))
        self.assertEqual(cached.decision, result.decision)
        self.assertEqual(cached.disposition, StateDisposition.CACHED)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        for path in self.root.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            raw = path.read_text()
            for secret in ("secret-project-path", "secret-session-id", "secret-call-id"):
                self.assertNotIn(secret, raw)
                self.assertNotIn(secret, path.name)

    def test_lock_publication_is_exclusive_then_opens_existing_without_create(self):
        original = os.open
        lock_flags = []
        def open_checked(path, flags, *args, **kwargs):
            if path == "state.lock":
                lock_flags.append(flags)
                # Deterministic regression for the observed concurrent first
                # publication path: O_CREAT without exclusivity is forbidden.
                if flags & os.O_CREAT and not flags & os.O_EXCL:
                    raise FileNotFoundError()
            return original(path, flags, *args, **kwargs)
        with mock.patch("router_core.state.os.open", side_effect=open_checked):
            self.assertEqual(self.store.run_once(self.scope, "first", decision).disposition, StateDisposition.COMPUTED)
        self.assertTrue(any(f & os.O_CREAT and f & os.O_EXCL for f in lock_flags))
        self.assertTrue(any(not f & os.O_CREAT for f in lock_flags))

    def test_disappearing_existing_lock_never_recreated_or_classifier_called(self):
        original = os.open
        lock_flags = []
        def disappearing(path, flags, *args, **kwargs):
            if path == "state.lock":
                lock_flags.append(flags)
                if flags & os.O_EXCL:
                    raise FileExistsError()
                raise FileNotFoundError()
            return original(path, flags, *args, **kwargs)
        with mock.patch("router_core.state.os.open", side_effect=disappearing):
            result = self.store.run_once(self.scope, "first", lambda: self.fail("provider called"))
        self.assertEqual(result.disposition, StateDisposition.ERROR)
        self.assertEqual(len(lock_flags), 2)
        self.assertFalse(lock_flags[-1] & os.O_CREAT)

    def test_twenty_independent_processes_call_classifier_once(self):
        ctx = multiprocessing.get_context("spawn")
        counter, ready, output = ctx.Value("i", 0), ctx.Event(), ctx.Queue()
        processes = [ctx.Process(target=_run_worker, args=(str(self.root), self.scope, "same", counter, ready, output)) for _ in range(20)]
        for process in processes:
            process.start()
        ready.set()
        results = [output.get(timeout=20) for _ in processes]
        for process in processes:
            process.join(20)
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(counter.value, 1)
        self.assertEqual(sum(status == "computed" for status, _ in results), 1)
        self.assertTrue(all(status in ("computed", "cached", "inflight") for status, _ in results), results)
        self.assertTrue(all(model in (None, "fixture-luna") for _, model in results))
        self.assertEqual(self.store.run_once(self.scope, "same", lambda: self.fail()).disposition, StateDisposition.CACHED)

    def test_parallel_different_keys_scopes_never_swap(self):
        ctx = multiprocessing.get_context("spawn")
        counter, ready, output = ctx.Value("i", 0), ctx.Event(), ctx.Queue()
        scopes = [StateScope("codex" if i % 2 else "claude", "project-" + str(i % 3), "session-" + str(i // 3)) for i in range(12)]
        processes = [ctx.Process(target=_run_worker, args=(str(self.root), scope, "key-"+str(i % 2), counter, ready, output, "model-" + str(i))) for i, scope in enumerate(scopes)]
        for process in processes:
            process.start()
        ready.set()
        results = [output.get(timeout=20) for _ in processes]
        for process in processes:
            process.join(20)
            self.assertEqual(process.exitcode, 0)
        self.assertTrue(all(status == "computed" for status, _ in results), results)
        self.assertEqual(counter.value, 12, results)
        self.assertEqual(set(model for _, model in results), {"model-"+str(i) for i in range(12)})
        for i, scope in enumerate(scopes):
            self.assertEqual(self.store.run_once(scope, "key-"+str(i % 2), lambda: self.fail()).decision.selected_model, "model-"+str(i))

    def test_process_crash_retains_claim_without_retry(self):
        ctx = multiprocessing.get_context("spawn")
        process = ctx.Process(target=_crash_worker, args=(str(self.root), self.scope))
        process.start()
        process.join(20)
        self.assertEqual(process.exitcode, 17)
        result = self.store.run_once(self.scope, "crashed-event", lambda: self.fail("reclassified crash"))
        self.assertEqual(result.disposition, StateDisposition.INFLIGHT)
        self.assertIsNone(result.decision)

    def test_callback_failure_sanitized_and_never_retried(self):
        def fail():
            raise RuntimeError("TOKEN=super-secret raw task text")
        result = self.store.run_once(self.scope, "failed", fail)
        self.assertEqual(str(result.error), "callback_failed")
        repeated = self.store.run_once(self.scope, "failed", lambda: self.fail("retried failure"))
        self.assertEqual(repeated.disposition, StateDisposition.ERROR)
        self.assertNotIn("super-secret", (self.root / "state.json").read_text())

    def test_invalid_callback_result_retains_claim(self):
        result = self.store.run_once(self.scope, "failed", lambda: {"task": "secret"})
        self.assertEqual(result.error.code, "callback_failed")
        self.assertEqual(self.store.run_once(self.scope, "failed", decision).disposition, StateDisposition.ERROR)

    def test_arbitrary_prose_not_persisted_in_decision(self):
        result = self.store.run_once(self.scope, "failed", lambda: RouteDecision("defer", "raw user task prose", "1", "root_prompt"))
        self.assertEqual(result.error.code, "callback_failed")
        self.assertNotIn("raw user", (self.root / "state.json").read_text())

    def test_capacity_never_evicts_retained_claims(self):
        clock = [1000.0]
        store = PrivateStateStore(self.root, max_records=1, ttl_seconds=10, clock=lambda: clock[0])
        self.assertEqual(store.run_once(self.scope, "first", decision).disposition, StateDisposition.COMPUTED)
        self.assertEqual(store.run_once(self.scope, "second", lambda: self.fail()).error.code, "capacity")
        clock[0] = 1009
        self.assertEqual(store.run_once(self.scope, "first", lambda: self.fail()).disposition, StateDisposition.CACHED)
        clock[0] = 1010
        self.assertEqual(store.run_once(self.scope, "second", decision).disposition, StateDisposition.COMPUTED)

    def test_expired_crashed_claim_can_only_retry_after_retention(self):
        clock = [1000.0]
        store = PrivateStateStore(self.root, ttl_seconds=10, clock=lambda: clock[0])
        class Interrupted(BaseException):
            pass
        def abort():
            raise Interrupted()
        with self.assertRaises(Interrupted):
            store.run_once(self.scope, "first", abort)
        self.assertEqual(store.run_once(self.scope, "first", lambda: self.fail()).disposition, StateDisposition.INFLIGHT)
        clock[0] = 1010
        self.assertEqual(store.run_once(self.scope, "first", decision).disposition, StateDisposition.COMPUTED)

    def test_byte_capacity_is_bounded_before_callback(self):
        store = PrivateStateStore(self.root, max_bytes=1024)
        calls = []
        for i in range(20):
            result = store.run_once(self.scope, str(i), lambda: (calls.append(1), decision())[1])
            if result.error:
                break
        self.assertEqual(result.error.code, "capacity")
        self.assertLessEqual((self.root / "state.json").stat().st_size, 1024)
        self.assertLess(len(calls), 20)

    def test_lock_wait_is_bounded_and_no_callback(self):
        self.store.run_once(self.scope, "first", decision)
        with (self.root / "state.lock").open("r+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            begin = time.monotonic()
            result = PrivateStateStore(self.root, lock_wait_seconds=0.02).run_once(self.scope, "other", lambda: self.fail())
            self.assertEqual(result.error.code, "lock_timeout")
            self.assertLess(time.monotonic() - begin, 0.5)

    def test_unsafe_root_mode_and_root_symlink_are_rejected(self):
        self.root.mkdir(mode=0o755)
        result = self.store.run_once(self.scope, "x", lambda: self.fail())
        self.assertEqual(result.disposition, StateDisposition.ERROR)
        self.root.rmdir()
        target = Path(self.temp.name) / "target"
        target.mkdir(mode=0o700)
        self.root.symlink_to(target, target_is_directory=True)
        self.assertEqual(self.store.run_once(self.scope, "x", lambda: self.fail()).disposition, StateDisposition.ERROR)
        self.assertEqual(list(target.iterdir()), [])

    def test_user_controlled_ancestor_symlink_rejected(self):
        target = Path(self.temp.name) / "target"
        target.mkdir(mode=0o700)
        alias = Path(self.temp.name) / "alias"
        alias.symlink_to(target, target_is_directory=True)
        store = PrivateStateStore(alias / "private")
        self.assertEqual(store.run_once(self.scope, "x", lambda: self.fail()).disposition, StateDisposition.ERROR)
        self.assertFalse((target / "private").exists())

    def test_unsafe_file_modes_symlinks_hardlinks_fifo(self):
        for filename in ("state.lock", "state.json"):
            for kind in ("mode", "symlink", "hardlink", "fifo"):
                with self.subTest(filename=filename, kind=kind), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp) / "private"
                    store = PrivateStateStore(root)
                    store.run_once(self.scope, "seed", decision)
                    target = root / filename
                    target.unlink()
                    external = Path(temp) / "external"
                    external.write_text("untouched")
                    external.chmod(0o600)
                    if kind == "mode":
                        target.write_text("{}")
                        target.chmod(0o644)
                    elif kind == "symlink":
                        target.symlink_to(external)
                    elif kind == "hardlink":
                        os.link(external, target)
                    else:
                        os.mkfifo(target, 0o600)
                    start = time.monotonic()
                    result = store.run_once(self.scope, "unsafe", lambda: self.fail())
                    self.assertEqual(result.disposition, StateDisposition.ERROR)
                    self.assertLess(time.monotonic() - start, 0.5)
                    self.assertEqual(external.read_text(), "untouched")

    def test_corrupt_and_tampered_files_fail_open_without_callback(self):
        for raw in ("not-json", '{"schema":1,"schema":1}', '{"schema":1,"last_write":NaN,"records":{}}'):
            with self.subTest(raw=raw):
                self.store.run_once(self.scope, "seed", decision)
                state = self.root / "state.json"
                state.write_text(raw)
                result = self.store.run_once(self.scope, "unsafe", lambda: self.fail())
                self.assertEqual(result.error.code, "invalid_state")
                state.unlink()
        self.store.run_once(self.scope, "seed", decision)
        state = self.root / "state.json"
        original = json.loads(state.read_text())
        for mutation in ("scope", "decision", "schema", "extra", "expiry"):
            data = json.loads(json.dumps(original))
            record = next(iter(data["records"].values()))
            if mutation == "scope":
                record["scope"] = "0" * 64
            elif mutation == "decision":
                record["value"]["decision"]["selected_model"] = "raw task prose"
            elif mutation == "schema":
                data["schema"] = True
            elif mutation == "extra":
                record["task_text"] = "secret"
            else:
                record["expires"] = record["created"] + 86401
            state.write_text(json.dumps(data))
            result = self.store.run_once(self.scope, "unsafe", lambda: self.fail())
            self.assertEqual(result.error.code, "invalid_state", mutation)
        state.write_text(json.dumps(original))

    def test_clock_rollback_is_fail_open_not_reclassification(self):
        clock = [100.0]
        store = PrivateStateStore(self.root, clock=lambda: clock[0])
        store.run_once(self.scope, "one", decision)
        clock[0] = 99
        result = store.run_once(self.scope, "two", lambda: self.fail())
        self.assertEqual(result.error.code, "clock_regressed")

    def test_orphan_atomic_temporary_is_cleaned_without_following_links(self):
        self.store.run_once(self.scope, "one", decision)
        orphan = self.root / (".tmp-" + "a" * 32)
        orphan.write_text("incomplete")
        orphan.chmod(0o600)
        self.store.run_once(self.scope, "two", decision)
        self.assertFalse(orphan.exists())
        external = Path(self.temp.name) / "external"
        external.write_text("untouched")
        orphan.symlink_to(external)
        result = self.store.run_once(self.scope, "three", lambda: self.fail())
        self.assertEqual(result.disposition, StateDisposition.ERROR)
        self.assertEqual(external.read_text(), "untouched")

    def test_prepared_reference_scope_ttl_replay_and_attestation(self):
        clock = [100.0]
        store = PrivateStateStore(self.root, clock=lambda: clock[0])
        reference = store.issue_prepared(self.scope, decision(), ttl_seconds=10)
        self.assertRegex(reference, r"^router_[0-9a-f]{48}$")
        raw = (self.root / "state.json").read_text()
        self.assertNotIn(reference, raw)
        for scope in (StateScope("claude", self.scope.project_id, self.scope.session_id),
                      StateScope("codex", "wrong", self.scope.session_id),
                      StateScope("codex", self.scope.project_id, "wrong")):
            self.assertIsNone(store.consume_prepared(scope, reference))
        consumed = store.consume_prepared(self.scope, reference)
        self.assertEqual(consumed.provenance, "orchestrator_attested")
        self.assertEqual(consumed.selected_model, "fixture-luna")
        self.assertIsNone(store.consume_prepared(self.scope, reference))
        reference = store.issue_prepared(self.scope, decision(), ttl_seconds=10)
        clock[0] = 110
        self.assertIsNone(store.consume_prepared(self.scope, reference))
        self.assertIsNone(store.consume_prepared(self.scope, "../state.json"))
        for ttl in (0, -1, 301, float("inf"), True):
            with self.assertRaises(StateError):
                store.issue_prepared(self.scope, decision(), ttl_seconds=ttl)

    def test_prepared_reference_concurrent_consumption_is_single_use(self):
        reference = self.store.issue_prepared(self.scope, decision())
        ctx = multiprocessing.get_context("spawn")
        ready, output = ctx.Event(), ctx.Queue()
        processes = [ctx.Process(target=_consume_worker, args=(str(self.root), self.scope, reference, ready, output)) for _ in range(20)]
        for process in processes:
            process.start()
        ready.set()
        results = [output.get(timeout=20) for _ in processes]
        for process in processes:
            process.join(20)
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(results.count("fixture-luna"), 1)
        self.assertEqual(results.count(None), 19)

    def test_boundary_receipts_native_ids_objectives_are_hashed_and_atomic(self):
        event = BoundaryEvent(self.scope, Lifecycle.TASK_CREATED, 1, event_id="secret-event", turn_id="secret-turn", task_id="secret-native", trusted_native=True)
        first = self.store.apply_boundary(event)
        self.assertEqual(first.classification, BoundaryClass.NEW_TASK)
        repeated = PrivateStateStore(self.root).apply_boundary(event)
        self.assertTrue(repeated.duplicate)
        linked = self.store.apply_boundary(BoundaryEvent(self.scope, Lifecycle.USER_PROMPT, 2,
            event_id="second-event", linked_task_id="secret-native", prompt="secret prompt words"))
        self.assertEqual(linked.classification, BoundaryClass.CONTINUATION)
        completed = self.store.apply_boundary(BoundaryEvent(self.scope, Lifecycle.TASK_COMPLETED, 3, task_id="secret-native", trusted_native=True))
        self.assertEqual(completed.reason, "trusted_task_completed")
        raw = (self.root / "state.json").read_text()
        for forbidden in ("secret-native", "secret-event", "secret-turn", "secret prompt", self.scope.project_id, self.scope.session_id):
            self.assertNotIn(forbidden, raw)
        self.assertEqual(self.store.get_boundary(StateScope("codex", "unrelated", "session")).receipts, ())

    def test_boundary_objective_vocabulary_is_never_persisted(self):
        self.store.apply_boundary(BoundaryEvent(self.scope, Lifecycle.USER_PROMPT, 1,
            event_id="e", prompt="Please implement private nebulanectar dashboard widgets with expandable columns and cards"))
        self.assertNotIn("nebulanectar", (self.root / "state.json").read_text())
        self.assertTrue(self.store.get_boundary(self.scope).objective_terms)

    def test_warning_and_observation_reset_preserves_warning_history(self):
        self.assertTrue(self.store.claim_warning(self.scope, "secret-warning"))
        self.assertFalse(PrivateStateStore(self.root).claim_warning(self.scope, "secret-warning"))
        self.store.observe_root(self.scope, model="gpt-6.1-sol", effort="medium")
        self.assertEqual(self.store.get_root(self.scope), {"model": "gpt-6.1-sol", "effort": "medium"})
        self.store.apply_boundary(BoundaryEvent(self.scope, Lifecycle.RESUME, 1))
        self.assertEqual(self.store.get_root(self.scope), {"model": None, "effort": None})
        self.assertFalse(self.store.claim_warning(self.scope, "secret-warning"))
        self.assertTrue(self.store.claim_warning(StateScope("codex", "another", "session"), "secret-warning"))
        self.assertNotIn("secret-warning", (self.root / "state.json").read_text())
        self.store.observe_root(self.scope, model=None, effort=None)
        self.assertEqual(self.store.get_root(self.scope), {"model": None, "effort": None})

    def test_atomic_write_failure_before_claim_never_invokes_callback(self):
        with mock.patch("router_core.state.os.replace", side_effect=OSError("secret filesystem path")):
            result = self.store.run_once(self.scope, "one", lambda: self.fail("claim not durable"))
        self.assertEqual(result.error.code, "state_io")
        self.assertNotIn("secret", str(result.error))
        self.assertEqual([p.name for p in self.root.iterdir()], ["state.lock"])
        self.assertEqual(self.store.run_once(self.scope, "one", decision).disposition, StateDisposition.COMPUTED)

    def test_post_callback_write_failure_retains_claim_not_decision(self):
        original = self.store._finish
        def broken_finish(*args):
            with mock.patch("router_core.state.os.replace", side_effect=OSError("secret")):
                return original(*args)
        with mock.patch.object(self.store, "_finish", side_effect=broken_finish):
            result = self.store.run_once(self.scope, "one", decision)
        self.assertEqual(result.disposition, StateDisposition.ERROR)
        self.assertIsNone(result.decision)
        self.assertEqual(PrivateStateStore(self.root).run_once(self.scope, "one", lambda: self.fail("retried")).disposition,
                         StateDisposition.INFLIGHT)

    def test_boundary_tampering_cannot_inject_raw_receipts_or_native_identity(self):
        self.store.apply_boundary(BoundaryEvent(self.scope, Lifecycle.TASK_CREATED, 1, task_id="native", trusted_native=True))
        path = self.root / "state.json"
        original = json.loads(path.read_text())
        for field, value in (("native_task_id", "raw-user-id"), ("objective_terms", ["rawtask"]),
                             ("warned_fingerprints", ["raw-warning"]), ("next_task_number", True),
                             ("receipts", [{"key": "user_prompt:event:raw-event", "classification": "new_task",
                                             "reason": "test", "logical_task_id": None}])):
            data = json.loads(json.dumps(original))
            next(iter(data["records"].values()))["value"][field] = value
            path.write_text(json.dumps(data))
            with self.assertRaises(StateError) as raised:
                self.store.get_boundary(self.scope)
            self.assertEqual(raised.exception.code, "invalid_state")

    def test_invalid_configuration_and_inputs(self):
        for kwargs in ({"ttl_seconds": 0}, {"max_records": 0}, {"max_bytes": 10}, {"lock_wait_seconds": float("nan")}, {"ttl_seconds": True}):
            with self.assertRaises(StateError):
                PrivateStateStore(self.root, **kwargs)
        self.assertEqual(self.store.run_once("not-scope", "id", decision).error.code, "invalid_input")
        self.assertEqual(self.store.run_once(self.scope, "", decision).error.code, "invalid_input")
        with self.assertRaises(StateError):
            self.store.apply_boundary({})
        with self.assertRaises(StateError):
            self.store.observe_root(self.scope, model="secret raw prose", effort=None)


if __name__ == "__main__":
    unittest.main()

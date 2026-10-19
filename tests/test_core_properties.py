"""Seeded/metamorphic offline invariants, not proof of native host support."""
import copy
from dataclasses import replace
import itertools
from pathlib import Path
import random
import tempfile
import unittest

from router_core.boundary import BoundaryEvent, Lifecycle
from router_core.normalizer import normalize_response
from router_core.config import merge_config_layers
from router_core.contracts import ProviderResult, ProviderStatus
from router_core.native import NativeAdapter, bootstrap_profile
from router_core.policy import assess
from router_core.privacy import SYNTHETIC_SMOKE
from router_core.spawn import AssessmentTracker, SpawnStatus, assess_child_spawn
from router_core.state import PrivateStateStore, StateScope, StateDisposition
from test_core_classifier import response
from test_core_policy import fixture
from test_core_spawn import claude_profile, codex_profile
from test_core_state import decision


class NormalizationProperties(unittest.TestCase):
    def test_seeded_permutations_scale_scores_and_preserve_min_confidence(self):
        rng = random.Random(34018)
        fields = ("tier", "risk", "complexity", "reasoning", "tool_complexity")
        for index in range(200):
            raw = response()
            for name in fields:
                raw[name]["confidence"] = rng.random()
            for name in fields[2:]:
                raw[name]["score"] = rng.uniform(0, 2)
            before = copy.deepcopy(raw)
            pairs = list(raw.items())
            rng.shuffle(pairs)
            shuffled = dict(pairs)
            for name in fields:
                shuffled[name] = dict(reversed(list(raw[name].items())))
            with self.subTest(index=index):
                actual = normalize_response(shuffled)
                self.assertEqual(actual, normalize_response(raw))
                self.assertEqual(raw, before)
                self.assertEqual(actual.confidence, min(raw[n]["confidence"] for n in fields))
                for name in fields[2:]:
                    self.assertEqual(getattr(actual, name), raw[name]["score"] / 2)
                lowered = copy.deepcopy(raw)
                lowered[fields[index % len(fields)]]["confidence"] = 0
                self.assertEqual(normalize_response(lowered).confidence, 0)

    def test_invalid_score_or_confidence_in_any_answer_never_normalizes(self):
        for name, value in itertools.product(
            ("tier", "risk", "complexity", "reasoning", "tool_complexity"),
            (True, None, "0.5", float("nan"), float("inf"), -0.001, 1.001),
        ):
            raw = response()
            raw[name]["confidence"] = value
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                normalize_response(raw)
        for name, value in itertools.product(
            ("complexity", "reasoning", "tool_complexity"),
            (True, None, "1", float("nan"), float("inf"), -0.001, 2.001),
        ):
            raw = response()
            raw[name]["score"] = value
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                normalize_response(raw)


class PrecedenceProperties(unittest.TestCase):
    def test_pins_win_over_invalid_host_schema_task_and_context_without_claiming(self):
        for profile, pin, value, invalid in itertools.product(
            (claude_profile(), codex_profile()),
            ("model", "effort", "reasoning_effort"),
            ("", "native-choice", False, 0, [], {}),
            ("host", "schema", "context"),
        ):
            tool = next(iter(profile.tools))
            # Deliberately malformed task: a pin still bypasses before inspection.
            args = {profile.tools[tool].task_field: {"not": "text"}, pin: value}
            original = copy.deepcopy(args)
            tracker = AssessmentTracker()
            kwargs = dict(profile=profile, event_name="PreToolUse",
                          event_schema_version=profile.input_schema_version,
                          tool_name=tool, tool_input=args, host_version=profile.host_version,
                          surface=profile.surface, project_id="p", session_id="s",
                          tool_use_id="same", tracker=tracker)
            kwargs.update({"host_version": "unverified"} if invalid == "host" else
                          {"event_schema_version": "unverified"} if invalid == "schema" else
                          {"session_id": None})
            with self.subTest(runtime=profile.runtime, pin=pin, value=value, invalid=invalid):
                result = assess_child_spawn(**kwargs)
                self.assertEqual(result.status, SpawnStatus.PINNED)
                self.assertIsNone(result.envelope)
                self.assertEqual(args, original)
                # Removing just the pin now exposes the original host/schema guard,
                # not a duplicate claim consumed by the earlier pinned attempt.
                args.pop(pin)
                self.assertEqual(assess_child_spawn(**kwargs).status, SpawnStatus.ABSTAIN)
                kwargs.update(host_version=profile.host_version,
                              event_schema_version=profile.input_schema_version, session_id="s",
                              tool_input={profile.tools[tool].task_field: "Synthetic task"})
                self.assertEqual(assess_child_spawn(**kwargs).status,
                    SpawnStatus.ELIGIBLE if profile.runtime.value == "claude" else SpawnStatus.PREPARED_TASK_REQUIRED)

    def test_null_and_absent_pins_expose_same_unsupported_host_guard(self):
        profile = claude_profile()
        for pin in ("model", "effort", "reasoning_effort"):
            for args in ({"prompt": "Task"}, {"prompt": "Task", pin: None}):
                result = assess_child_spawn(profile=profile, event_name="PreToolUse",
                    event_schema_version=profile.input_schema_version, tool_name="Agent",
                    tool_input=args, host_version="future", surface="cli", project_id="p",
                    session_id="s", tool_use_id="t", tracker=AssessmentTracker())
                self.assertEqual(result.reason_code, "unsupported_host_version")

    def test_cheap_policy_guards_dominate_provider_faults_in_cross_product(self):
        for runtime, mode, custom, pinned in itertools.product(
            ("claude", "codex"), ("disabled", "warn", "auto_workers", "shadow"),
            (False, True), (False, True),
        ):
            if not (custom or pinned or mode in ("disabled", "warn")):
                continue
            env, _, catalog, config, scope = fixture({"runtime": runtime,
                "options": {"mode": mode, "custom": custom, "explicit_model": "" if pinned else None}})
            before = env.to_dict()
            calls = []
            def forbidden(_):
                calls.append(1)
                raise RuntimeError("provider fault")
            result = assess(env, forbidden, catalog, config, scope)
            self.assertEqual(calls, [])
            self.assertEqual(result.disposition.value, "skip")
            self.assertIsNone(result.selected_model)
            self.assertEqual(env.to_dict(), before)


class StateIsolationProperties(unittest.TestCase):
    def test_permuted_scopes_isolate_replays_failures_prepared_and_root_state(self):
        scopes = [StateScope(*parts) for parts in itertools.product(
            ("claude", "codex"), ("project-a", "project-b"), ("session-a", "session-b"))]
        for seed in (34, 180, 200):
            with self.subTest(seed=seed), tempfile.TemporaryDirectory() as tmp:
                store = PrivateStateStore(Path(tmp) / "private")
                order = list(range(len(scopes)))
                random.Random(seed).shuffle(order)
                calls, references = [], {}
                for i in order:
                    scope = scopes[i]
                    def callback(i=i):
                        calls.append(i)
                        if i % 3 == 0:
                            raise RuntimeError("private-error")
                        return decision("fixture-" + str(i))
                    result = store.run_once(scope, "same-call", callback)
                    self.assertEqual(result.disposition,
                        StateDisposition.ERROR if i % 3 == 0 else StateDisposition.COMPUTED)
                    references[i] = store.issue_prepared(scope, decision("fixture-" + str(i)))
                    store.observe_root(scope, model="root-" + str(i), effort="medium")
                    store.apply_boundary(BoundaryEvent(scope, Lifecycle.PREFLIGHT, 100,
                        event_id="same-event", prompt="Review synthetic tests"))
                self.assertCountEqual(calls, range(len(scopes)))
                task_ids = [store.get_boundary(scope).logical_task_id for scope in scopes]
                self.assertTrue(all(task_ids))
                self.assertEqual(len(set(task_ids)), len(scopes))
                for i in reversed(order):
                    scope = scopes[i]
                    result = store.run_once(scope, "same-call", lambda: self.fail("replayed callback"))
                    self.assertEqual(result.disposition,
                        StateDisposition.ERROR if i % 3 == 0 else StateDisposition.CACHED)
                    if i % 3:
                        self.assertEqual(result.decision.selected_model, "fixture-" + str(i))
                    self.assertEqual(store.get_root(scope)["model"], "root-" + str(i))
                    for j in order:
                        if i != j:
                            self.assertIsNone(store.consume_prepared(scope, references[j]))
                    self.assertEqual(store.consume_prepared(scope, references[i]).selected_model,
                                     "fixture-" + str(i))
                    self.assertIsNone(store.consume_prepared(scope, references[i]))
                # A lifecycle reset clears only its own root; later observation
                # and a distinct event key remain isolated from retained claims.
                store.apply_boundary(BoundaryEvent(scopes[0], Lifecycle.COMPACTION, 101,
                                                   event_id="same-event-reset"))
                self.assertIsNone(store.get_root(scopes[0])["model"])
                for i in range(1, len(scopes)):
                    self.assertEqual(store.get_root(scopes[i])["model"], "root-" + str(i))
                store.observe_root(scopes[0], model="root-after-reset")
                self.assertEqual(store.get_root(scopes[0])["model"], "root-after-reset")
                self.assertEqual(store.run_once(scopes[0], "another-call", decision).disposition,
                                 StateDisposition.COMPUTED)


class NativeNoOpProperties(unittest.TestCase):
    def test_failed_provider_and_unsupported_host_leave_native_inputs_untouched(self):
        for runtime, fault in itertools.product(("claude", "codex"),
                ("unknown_version", "provider_failure", "opaque", "multimodal")):
            with self.subTest(runtime=runtime, fault=fault), tempfile.TemporaryDirectory() as tmp:
                project = str(Path(tmp).resolve())
                version = "2.1.303" if runtime == "claude" else "0.163.0"
                profile = bootstrap_profile(runtime, "cli", "future" if fault == "unknown_version" else version)
                if profile:
                    profile = replace(profile, conflicts_checked=True,
                        safe_rewrite_permission_modes=frozenset({"default"}))
                config = merge_config_layers({"mode": "auto_workers",
                    "consent": {"synthetic_tasks": True}}, {})
                calls = []
                def failed(_):
                    calls.append(1)
                    return ProviderResult(ProviderStatus.FAILURE, reason_code="timeout")
                adapter = NativeAdapter(profile, config, PrivateStateStore(Path(project) / "state"),
                                        failed, project_id=project)
                args = ({"prompt": SYNTHETIC_SMOKE, "description": "Synthetic fixture"}
                        if runtime == "claude" else {"message": "gAAAA_opaque_fixture", "task_name": "ordinary_task"})
                if fault == "multimodal":
                    args = {"prompt" if runtime == "claude" else "items":
                            [{"type": "image", "data": "synthetic-not-an-image"}]}
                event = dict(cwd=project, session_id="s", hook_event_name="PreToolUse",
                    permission_mode="default", tool_name="Agent" if runtime == "claude" else "collaborationspawn_agent",
                    tool_input=args, tool_use_id="t")
                before = copy.deepcopy(event)
                original_args = event["tool_input"]
                self.assertIsNone(adapter.handle(event))
                self.assertEqual(event, before)
                self.assertIs(event["tool_input"], original_args)
                expected_calls = int(runtime == "claude" and fault in ("provider_failure", "opaque"))
                self.assertEqual(len(calls), expected_calls)

    def test_text_only_codex_items_are_not_invented_plaintext_capability(self):
        profile = codex_profile()
        args = {"items": [{"type": "text", "text": SYNTHETIC_SMOKE}], "task_name": "ordinary"}
        before = copy.deepcopy(args)
        result = assess_child_spawn(profile=profile, event_name="PreToolUse",
            event_schema_version=profile.input_schema_version, tool_name="collaborationspawn_agent",
            tool_input=args, host_version=profile.host_version, surface=profile.surface,
            project_id="p", session_id="s", tool_use_id="t", tracker=AssessmentTracker())
        self.assertEqual(result.status, SpawnStatus.ABSTAIN)
        self.assertIsNone(result.envelope)
        self.assertEqual(args, before)

    def test_taskcreated_payload_cannot_attest_root_identity(self):
        for runtime in ("claude", "codex"):
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as tmp:
                project = str(Path(tmp).resolve())
                store = PrivateStateStore(Path(project) / "state")
                scope = StateScope(runtime, project, "session")
                store.observe_root(scope, model="known-root", effort="medium")
                store.apply_boundary(BoundaryEvent(scope, Lifecycle.PREFLIGHT, 100,
                    event_id="known-event", prompt="Review synthetic tests"))
                before_task = store.get_boundary(scope).logical_task_id
                profile = bootstrap_profile(runtime, "cli", "2.1.303" if runtime == "claude" else "0.163.0")
                calls = []
                adapter = NativeAdapter(profile,
                    merge_config_layers({"mode": "auto_workers"}, {}), store,
                    lambda _: calls.append(1), project_id=project, clock=lambda: 101)
                for i, extra in enumerate(({}, {"agent_id": "nested-worker"})):
                    event = dict(cwd=project, session_id="session", hook_event_name="TaskCreated",
                        event_id="forged-" + str(i), task_id="forged-root", model="forged-model",
                        effort="high", trusted_native=True, root_provenance="root", **extra)
                    before = copy.deepcopy(event)
                    self.assertIsNone(adapter.handle(event))
                    self.assertEqual(event, before)
                    self.assertEqual(store.get_boundary(scope).logical_task_id, before_task)
                    self.assertEqual(store.get_root(scope), {"model": "known-root", "effort": "medium"})
                self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()

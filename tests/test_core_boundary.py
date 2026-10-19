import unittest

from router_core.boundary import (
    BoundaryClass,
    BoundaryEvent,
    BoundaryScope,
    Lifecycle,
    TaskStatus,
    initial_state,
    mark_warning,
    transition,
)


class RootBoundaryTests(unittest.TestCase):
    def test_older_clock_sample_on_known_replay_does_not_invalidate_active_task(self):
        event = BoundaryEvent(BoundaryScope("codex", "/project/demo", "session-1"),
            Lifecycle.USER_PROMPT, 10, turn_id="same-turn", prompt="/new-task Implement example validation")
        state = transition(initial_state(event.scope), event).state
        replay = BoundaryEvent(event.scope, Lifecycle.USER_PROMPT, 9,
            turn_id="same-turn", prompt=event.prompt)
        result = transition(state, replay)
        self.assertTrue(result.duplicate)
        self.assertEqual(result.state, state)

    def setUp(self):
        self.scope = BoundaryScope("codex", "/project/demo", "session-1")
        self.state = initial_state(self.scope)
        self.event_number = 0

    def event(self, kind=Lifecycle.USER_PROMPT, at=1, **kwargs):
        if "event_id" not in kwargs and "turn_id" not in kwargs:
            self.event_number += 1
            kwargs["event_id"] = "event-{}".format(self.event_number)
        return BoundaryEvent(self.scope, kind, at, **kwargs)

    def apply(self, event):
        result = transition(self.state, event)
        self.state = result.state
        return result

    def test_distinct_native_tasks_in_one_turn_are_not_duplicate(self):
        first = self.apply(self.event(Lifecycle.TASK_CREATED, at=1, task_id="task-a",
                                     turn_id="same-turn", trusted_native=True))
        second = self.apply(self.event(Lifecycle.TASK_CREATED, at=2, task_id="task-b",
                                      turn_id="same-turn", trusted_native=True))
        self.assertEqual(first.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(second.classification, BoundaryClass.NEW_TASK)
        self.assertNotEqual(first.logical_task_id, second.logical_task_id)

    def test_explicit_new_request_can_share_prior_objective_vocabulary(self):
        first = self.apply(self.event(prompt="Implement authentication middleware with account validation and audit logging"))
        second = self.apply(self.event(at=2, prompt="New task: Review authentication middleware for security risks and missing unit tests"))
        self.assertEqual(second.classification, BoundaryClass.NEW_TASK)
        self.assertNotEqual(first.logical_task_id, second.logical_task_id)

    def test_objective_vocabulary_not_retained_even_in_hidden_fields(self):
        self.apply(self.event(prompt="Implement confidential invoice reconciliation and audit report export functionality"))
        self.assertTrue(self.state.objective_terms)
        self.assertNotIn("confidential", self.state.objective_terms)
        self.assertNotIn("invoice", self.state.objective_terms)
        self.assertTrue(all(len(term) == 32 for term in self.state.objective_terms))

    def test_root_identity_includes_project_scope_without_exposing_it(self):
        event = self.event(prompt="/new-task Implement the new example task")
        first = transition(initial_state(self.scope), event)
        other_scope = BoundaryScope("codex", "/project/other", "session-1")
        other = BoundaryEvent(other_scope, Lifecycle.USER_PROMPT, 1, event_id=event.event_id, prompt=event.prompt)
        second = transition(initial_state(other_scope), other)
        self.assertNotEqual(first.logical_task_id, second.logical_task_id)
        self.assertNotIn("session-1", first.logical_task_id)

    def test_invalid_lifecycle_does_not_echo_untrusted_text(self):
        with self.assertRaises(ValueError) as error:
            BoundaryEvent(self.scope, "private-secret-lifecycle", 0)
        self.assertNotIn("private-secret", str(error.exception))

    def test_first_standalone_objective_is_new_and_raw_text_not_retained(self):
        prompt = "Implement the invoice reconciliation flow with deterministic audit logging"
        result = self.apply(self.event(prompt=prompt, turn_id="turn-1"))
        self.assertEqual(result.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(result.reason, "standalone_initial_objective")
        self.assertNotIn(prompt, repr(result.state))
        self.assertNotIn("invoice", repr(result.state))
        self.assertTrue(result.logical_task_id)

    def test_short_acknowledgements_suppress_in_english_and_portuguese(self):
        for prompt in ("yes", "OK!", "go ahead", "Sim, por favor.", "pode ser"):
            with self.subTest(prompt=prompt):
                state = initial_state(self.scope)
                first = transition(state, self.event(prompt="Create a migration for account reconciliation with strict validation", at=1))
                result = transition(first.state, self.event(prompt=prompt, at=2))
                self.assertEqual(result.classification, BoundaryClass.CONTINUATION)
                self.assertEqual(result.reason, "clear_acknowledgement")

    def test_ambiguous_prompts_abstain_and_overlap_does_not_prove_new_task(self):
        first = self.apply(self.event(prompt="Implement account reconciliation with strict validation and complete audit records", at=1))
        self.assertEqual(first.classification, BoundaryClass.NEW_TASK)
        for prompt in ("Can you also update account reconciliation tests and validation?", "fix it"):
            result = self.apply(self.event(prompt=prompt, at=2))
            self.assertIn(result.classification, (BoundaryClass.UNKNOWN, BoundaryClass.CONTINUATION))
            self.assertNotEqual(result.classification, BoundaryClass.NEW_TASK)

    def test_disjoint_vocabulary_alone_is_not_new_task_but_explicit_topic_shift_is(self):
        first = self.apply(self.event(prompt="Design the invoice reconciliation workflow with durable audit records", at=1))
        continuation = self.apply(self.event(prompt="Research botanical garden accessibility maps for weekend visitors", at=2))
        second = self.apply(self.event(prompt="New task: Research botanical garden accessibility maps for weekend visitors", at=3))
        self.assertEqual(first.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(continuation.classification, BoundaryClass.UNKNOWN)
        self.assertEqual(continuation.reason, "objective_change_not_proven")
        self.assertEqual(second.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(second.reason, "explicit_topic_shift")
        self.assertNotEqual(first.logical_task_id, second.logical_task_id)

    def test_long_log_or_narrative_with_disjoint_words_is_not_objective(self):
        first = self.apply(self.event(prompt="Implement account reconciliation with strict validation and complete audit records", at=1))
        log = "Traceback from garden server shows visitor counts and botanical maps after network timeout in production"
        result = self.apply(self.event(prompt=log, at=2))
        narrative = "Yesterday the museum described a new inventory forecast and shipping policy to regional staff"
        result2 = self.apply(self.event(prompt=narrative, at=3))
        self.assertEqual(first.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(result.classification, BoundaryClass.UNKNOWN)
        self.assertEqual(result2.classification, BoundaryClass.UNKNOWN)
        self.assertNotIn("garden", repr(self.state))

    def test_portuguese_request_intent_and_explicit_topic_shift(self):
        first = self.apply(self.event(prompt="Crie uma rotina de reconciliacao financeira com validacao e trilha de auditoria", at=1))
        second = self.apply(self.event(prompt="Nova tarefa: Pesquise acessibilidade de jardins botanicos para visitantes", at=2))
        self.assertEqual(first.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(second.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(second.reason, "explicit_topic_shift")

    def test_new_task_marker_must_be_leading_not_quoted_or_in_code(self):
        for prompt in ('The docs say "/new-task Design a clean schema for regional inventory records"',
                       '```text\n/new-task Design a clean schema for regional inventory records\n```'):
            result = transition(initial_state(self.scope), self.event(prompt=prompt, at=1))
            self.assertEqual(result.classification, BoundaryClass.UNKNOWN)
        leading = transition(initial_state(self.scope), self.event(prompt="  /new-task Design a clean schema for regional inventory records", at=1))
        self.assertEqual(leading.classification, BoundaryClass.NEW_TASK)

    def test_new_task_classification_requires_stable_event_or_turn_id(self):
        no_identity = BoundaryEvent(self.scope, Lifecycle.USER_PROMPT, 1,
                                    prompt="Implement a careful billing reconciliation audit pipeline across multiple configured accounts")
        result = transition(initial_state(self.scope), no_identity)
        self.assertEqual(result.classification, BoundaryClass.UNKNOWN)
        self.assertEqual(result.reason, "missing_event_identity")
        self.assertIsNone(result.state.logical_task_id)
        no_identity_preflight = BoundaryEvent(self.scope, Lifecycle.PREFLIGHT, 2)
        preflight = transition(result.state, no_identity_preflight)
        self.assertEqual(preflight.classification, BoundaryClass.UNKNOWN)
        self.assertEqual(preflight.reason, "missing_event_identity")

    def test_explicit_preflight_and_marker_are_structural_new_tasks(self):
        marker = self.apply(self.event(prompt="/new-task Draft a new analytics migration proposal", at=1, turn_id="t1"))
        preflight = self.apply(self.event(Lifecycle.PREFLIGHT, at=2, event_id="preflight-1"))
        self.assertEqual(marker.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(marker.reason, "explicit_new_task_marker")
        self.assertEqual(preflight.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(preflight.reason, "explicit_preflight")

    def test_trusted_native_task_created_is_new_and_same_task_is_continuation(self):
        created = self.apply(self.event(Lifecycle.TASK_CREATED, at=1, task_id="native-7", trusted_native=True,
                                        event_id="created-7"))
        repeated = self.apply(self.event(Lifecycle.TASK_CREATED, at=2, task_id="native-7", trusted_native=True,
                                         event_id="created-7b"))
        linked = self.apply(self.event(prompt="Please continue", at=3, linked_task_id="native-7"))
        self.assertEqual(created.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(repeated.classification, BoundaryClass.CONTINUATION)
        self.assertEqual(linked.classification, BoundaryClass.CONTINUATION)
        self.assertEqual(created.logical_task_id, repeated.logical_task_id)
        parent_linked = self.apply(self.event(Lifecycle.TASK_CREATED, at=4, task_id="native-child",
                                              linked_task_id="native-7", trusted_native=True,
                                              event_id="created-child"))
        self.assertEqual(parent_linked.classification, BoundaryClass.CONTINUATION)
        self.assertEqual(parent_linked.logical_task_id, created.logical_task_id)

    def test_untrusted_task_created_and_child_spawn_never_trigger_root(self):
        untrusted = self.apply(self.event(Lifecycle.TASK_CREATED, at=1, task_id="fake", trusted_native=False))
        child = self.apply(self.event(Lifecycle.SUBAGENT_SPAWN, at=2, task_id="child-1", trusted_native=True))
        self.assertEqual(untrusted.classification, BoundaryClass.UNKNOWN)
        self.assertEqual(child.classification, BoundaryClass.UNKNOWN)
        self.assertEqual(child.reason, "child_task_not_root")
        self.assertIsNone(self.state.logical_task_id)

        root = self.apply(self.event(Lifecycle.TASK_CREATED, at=3, task_id="root-native",
                                     trusted_native=True, event_id="root-created"))
        child = self.apply(self.event(Lifecycle.SUBAGENT_SPAWN, at=4, task_id="child-2",
                                      trusted_native=True, event_id="spawn-2"))
        self.assertEqual(root.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(child.classification, BoundaryClass.UNKNOWN)
        self.assertEqual(child.logical_task_id, root.logical_task_id)
        self.assertEqual(self.state.native_task_id, "root-native")

    def test_tool_loops_and_stop_never_classify_or_complete(self):
        created = self.apply(self.event(prompt="Implement the payment ledger with idempotent settlement checks", at=1))
        logical_id = created.logical_task_id
        tool = self.apply(self.event(Lifecycle.TOOL_ACTIVITY, at=2, event_id="tool-1"))
        stopped = self.apply(self.event(Lifecycle.STOP, at=3, event_id="stop-1"))
        self.assertEqual(tool.classification, BoundaryClass.UNKNOWN)
        self.assertEqual(stopped.reason, "stop_not_completion")
        self.assertEqual(self.state.status, TaskStatus.ACTIVE)
        self.assertEqual(self.state.logical_task_id, logical_id)

    def test_duplicate_turn_or_event_cannot_retrigger_new_task(self):
        event = self.event(prompt="Create a robust notification scheduler with retries and observability", at=1,
                           turn_id="turn-dup")
        first = self.apply(event)
        duplicate = self.apply(self.event(prompt=event.prompt, at=2, turn_id="turn-dup"))
        self.assertEqual(first.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(duplicate.classification, BoundaryClass.CONTINUATION)
        self.assertTrue(duplicate.duplicate)
        self.assertEqual(first.logical_task_id, duplicate.logical_task_id)

    def test_resume_and_compaction_clear_questionable_task_but_keep_same_scope_warning_dedupe(self):
        first = self.apply(self.event(prompt="Design reliable service discovery for internal network routing", at=1))
        self.state = mark_warning(self.state, "safe-fingerprint-1")
        resumed = self.apply(self.event(Lifecycle.RESUME, at=2, event_id="resume-1"))
        self.assertEqual(resumed.classification, BoundaryClass.UNKNOWN)
        self.assertEqual(self.state.status, TaskStatus.UNCERTAIN)
        self.assertIsNone(self.state.logical_task_id)
        self.assertIn("safe-fingerprint-1", self.state.warned_fingerprints)
        self.assertGreater(self.state.generation, 0)
        compacted = self.apply(self.event(Lifecycle.COMPACTION, at=3, event_id="compact-1"))
        self.assertEqual(compacted.classification, BoundaryClass.UNKNOWN)
        self.assertEqual(self.state.generation, 2)

    def test_same_turn_compaction_runs_before_receipt_dedupe(self):
        prompt = self.apply(self.event(prompt="Design reliable service discovery for internal network routing",
                                       at=1, event_id="shared", turn_id="same-turn"))
        compacted = self.apply(self.event(Lifecycle.COMPACTION, at=2,
                                          event_id="shared", turn_id="same-turn"))
        self.assertEqual(prompt.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(compacted.classification, BoundaryClass.UNKNOWN)
        self.assertEqual(compacted.reason, "compaction")
        self.assertIsNone(self.state.logical_task_id)
        self.assertEqual(self.state.status, TaskStatus.UNCERTAIN)

    def test_event_id_collision_across_kinds_does_not_suppress_stop(self):
        created = self.apply(self.event(Lifecycle.TASK_CREATED, at=1, task_id="native-1",
                                        trusted_native=True, event_id="shared-id"))
        stopped = self.apply(self.event(Lifecycle.STOP, at=2, event_id="shared-id"))
        self.assertEqual(created.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(stopped.reason, "stop_not_completion")
        self.assertFalse(stopped.duplicate)
        self.assertEqual(self.state.logical_task_id, created.logical_task_id)

    def test_ttl_only_discards_evidence_and_does_not_make_expired_prompt_new(self):
        first = self.apply(self.event(prompt="Build a careful permissions audit for project workspaces", at=10))
        expired = self.apply(self.event(prompt="Design an unrelated inventory forecasting tool for retailers", at=10 + 1801))
        self.assertEqual(first.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(expired.classification, BoundaryClass.UNKNOWN)
        self.assertEqual(expired.reason, "ttl_expired")

    def test_nonfinite_timestamps_and_ttl_are_rejected(self):
        for timestamp in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(timestamp=timestamp):
                with self.assertRaises(ValueError):
                    BoundaryEvent(self.scope, Lifecycle.USER_PROMPT, timestamp)
        for ttl in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(ttl=ttl):
                with self.assertRaises(ValueError):
                    transition(self.state, self.event(at=1), ttl_seconds=ttl)

    def test_backward_timestamp_invalidates_without_moving_monotonic_clock_back(self):
        created = self.apply(self.event(prompt="Design reliable service discovery for internal network routing", at=10))
        regressed = self.apply(self.event(prompt="Build a separate payments reconciliation flow with audit records", at=9))
        self.assertEqual(created.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(regressed.classification, BoundaryClass.UNKNOWN)
        self.assertEqual(regressed.reason, "clock_regressed")
        self.assertIsNone(self.state.logical_task_id)
        self.assertEqual(self.state.last_activity, 10)

    def test_explicit_completion_requires_trusted_matching_native_task(self):
        created = self.apply(self.event(Lifecycle.TASK_CREATED, at=1, task_id="task-1", trusted_native=True,
                                        event_id="created-task-1"))
        wrong = self.apply(self.event(Lifecycle.TASK_COMPLETED, at=2, task_id="task-other", trusted_native=True))
        done = self.apply(self.event(Lifecycle.TASK_COMPLETED, at=3, task_id="task-1", trusted_native=True))
        self.assertEqual(wrong.classification, BoundaryClass.UNKNOWN)
        self.assertEqual(self.state.status, TaskStatus.COMPLETED)
        self.assertEqual(done.reason, "trusted_task_completed")
        self.assertIsNone(done.logical_task_id)
        self.assertIsNotNone(created.logical_task_id)

    def test_scopes_do_not_share_task_or_warning_state(self):
        first = self.apply(self.event(prompt="Build reliable catalog synchronization with conflict checks across regions", at=1))
        self.state = mark_warning(self.state, "fingerprint")
        other_scope = BoundaryScope("claude", "/project/demo", "session-1")
        result = transition(self.state, BoundaryEvent(other_scope, Lifecycle.USER_PROMPT, 2,
                                                      prompt="Build reliable catalog synchronization with conflict checks across regions"))
        self.assertEqual(first.classification, BoundaryClass.NEW_TASK)
        self.assertEqual(result.classification, BoundaryClass.UNKNOWN)
        self.assertIsNone(result.state.logical_task_id)
        self.assertEqual(result.state.warned_fingerprints, ())

    def test_provider_call_budget_can_be_injected_without_provider_dependency(self):
        calls = []

        def driver(state, event):
            result = transition(state, event)
            if result.classification is BoundaryClass.NEW_TASK and not result.duplicate:
                calls.append(result.logical_task_id)
            return result

        prompt = "Implement a resilient webhook delivery engine with bounded retries"
        first = driver(self.state, self.event(prompt=prompt, at=1, event_id="e1"))
        continued = driver(first.state, self.event(prompt="Continue", at=2, event_id="e2"))
        tool = driver(continued.state, self.event(Lifecycle.TOOL_ACTIVITY, at=3))
        self.assertEqual(calls, [first.logical_task_id])
        self.assertEqual(tool.classification, BoundaryClass.UNKNOWN)

    def test_warning_history_is_bounded_and_idempotent(self):
        state = self.state
        for index in range(70):
            state = mark_warning(state, "fingerprint-{}".format(index))
        state = mark_warning(state, "fingerprint-69")
        self.assertEqual(len(state.warned_fingerprints), 64)
        self.assertEqual(state.warned_fingerprints[-1], "fingerprint-69")


if __name__ == "__main__":
    unittest.main()

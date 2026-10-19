import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.spikes import task_outcome_pilot as pilot


class TaskOutcomePilotTests(unittest.TestCase):
    def answer(self, task):
        return {"bug_line": task["bug_line"], "counterexample": task["known_counterexample"],
                "expected_json": json.dumps(task["known_expected"]), "actual_json": json.dumps(task["known_actual"])}

    def test_frozen_examples_and_nontrivial_oracle_for_each_task(self):
        tasks = pilot.load_tasks()
        self.assertEqual(len(tasks), 3)
        for task in tasks:
            self.assertTrue(pilot.grade(task, self.answer(task)))
            answer = self.answer(task); answer["expected_json"] = answer["actual_json"]
            self.assertFalse(pilot.grade(task, answer))
            answer = self.answer(task); answer["bug_line"] += 1
            self.assertFalse(pilot.grade(task, answer))
        # Different valid counterexamples, not string matching a canned answer.
        self.assertEqual(pilot.oracle("strict-positive", {"values": [-1, 0], "target": None}), (None, 0))
        self.assertEqual(pilot.oracle("binary-search-boundary", {"values": [2, 5], "target": 5}), (1, -1))

    def test_oracle_invalid_types_ranges_duplicate_and_non_json_answers_fail(self):
        task = pilot.load_tasks()[0]
        for patch_value in ({"bug_line": True}, {"expected_json": "true"}, {"actual_json": "false"},
                            {"actual_json": "0.0"}, {"expected_json": "NaN"}, {"expected_json": "[]"},
                            {"counterexample": {"values": [True], "target": None}},
                            {"counterexample": {"values": [1000], "target": None}},
                            {"counterexample": {"values": [0]*33, "target": None}},
                            {"counterexample": {"values": [0], "target": 1}}):
            answer = {**self.answer(task), **patch_value}
            self.assertFalse(pilot.grade(task, answer))
        for text in ('{"a":1,"a":2}', 'NaN'):
            with self.assertRaises(ValueError):
                pilot.decode(text)

    def test_trial_grades_actual_task_output_and_does_not_execute_code(self):
        task = pilot.load_tasks()[0]
        observed = []
        def native(binary, directory, prompt, schema, selection):
            observed.append((schema, selection, prompt))
            return {"status": "completed", "answer": self.answer(task), "elapsed_ms": 1,
                    "observed_models": ["claude-sonnet-5-5"], "observed_effort": None, "usage": {}}
        with patch.object(pilot, "native", side_effect=native), \
                patch.object(pilot, "JevClient", side_effect=AssertionError("provider forbidden")):
            result = pilot.trial(task, "no_router_parent_baseline", 0, "/fixture/claude", None)
        self.assertTrue(result["oracle_success"])
        self.assertIsNone(result["human_rework"])
        self.assertEqual(result["orchestrator_execution_attempts"], 1)
        self.assertEqual(result["orchestrator_retries"], 0)
        self.assertEqual(len(observed), 1)
        self.assertIn(task["source"], observed[0][2])
        self.assertNotIn("known_expected", observed[0][2])

    def test_parent_failure_is_retained_and_falls_back_without_hidden_retry(self):
        task = pilot.load_tasks()[1]
        replies = [{"status": "timeout", "elapsed_ms": 90000},
                   {"status": "completed", "answer": self.answer(task), "elapsed_ms": 1}]
        with patch.object(pilot, "native", side_effect=replies) as execute:
            result = pilot.trial(task, "parent_selection", 0, "/fixture/claude", None)
        self.assertEqual(execute.call_count, 2)  # one selection, one execution
        self.assertEqual(result["requested"], pilot.BASELINE)
        self.assertEqual(result["selection"]["status"], "timeout")
        self.assertTrue(result["selection"]["fallback"])
        self.assertEqual(result["orchestrator_execution_attempts"], 1)

    def test_native_launch_failure_is_a_measured_failed_call(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(pilot.subprocess, "Popen", side_effect=OSError("private detail")):
            result = pilot.native("/missing", directory, "fixture", pilot.ANSWER_SCHEMA, pilot.BASELINE)
        self.assertEqual(result["status"], "native_launch_or_io_failure")
        self.assertNotIn("private", json.dumps(result))

    def test_native_bounds_output_during_read_not_after_unbounded_allocation(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(pilot, "_capture", return_value=(-9, b"", b"", "output_limit", 2_097_152)) as capture:
            result = pilot.native("/fixture/claude", directory, "fixture", pilot.ANSWER_SCHEMA, pilot.BASELINE)
        self.assertEqual(result["status"], "output_limit")
        self.assertEqual(capture.call_args.args[1:], (90, 2_097_152))
        self.assertEqual(capture.call_args.kwargs["cwd"], directory)
        self.assertEqual(capture.call_args.kwargs["env"]["ROUTER_DISABLE"], "1")

    def test_summary_includes_parent_usage_and_keeps_missing_counters_unknown(self):
        rows = []
        for arm in pilot.ARMS:
            for i in range(3):
                rows.append({"arm": arm, "task_id": str(i), "total_ms": i+1, "oracle_success": i != 2,
                    "jev_callback_attempts": int(arm == "jev_policy"),
                    "execution": {"status": "timeout"} if i == 2 else {"usage": {"input_tokens": 10}},
                    "selection": {"usage": {"input_tokens": 2}}})
        summary = pilot.summarize(rows)
        self.assertEqual(summary["parent_selection"]["usage_counters_not_quota"]["input_tokens"],
            {"observed_sum": 26, "calls_with_counter": 5, "calls_missing_counter": 1})
        self.assertEqual(summary["parent_selection"]["oracle_successes"], 2)
        self.assertIsNone(summary["parent_selection"]["human_rework"])

    def test_task_cluster_interval_includes_all_failed_executions(self):
        rows = [{"task_id": str(i), "arm": "A", "oracle_success": i == 0} for i in range(3) for _ in range(2)]
        result = pilot.clustered_interval(rows, "A")
        self.assertEqual(result["clusters"], 3)
        self.assertEqual(result["lower"], 0)
        self.assertEqual(result["upper"], 1)


if __name__ == "__main__":
    unittest.main()

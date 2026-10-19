import json
import unittest
from unittest.mock import patch

from scripts.spikes import code_outcome_benchmark as bench


class CodeOutcomeTests(unittest.TestCase):
    def test_fixtures_validate_only_through_container_and_reject_weak_test_suite(self):
        seen = []
        def grade(source, tests, **kwargs):
            seen.append((source, tests, kwargs))
            return {"passed": len(seen)%2 == 1, "status": "passed" if len(seen)%2 else "failed",
                    "tests_run": 5, "cleanup_verified": True}
        with patch.object(bench, "grade_python", side_effect=grade), \
                patch.object(bench.strategies, "native", side_effect=AssertionError("model forbidden")):
            result = bench.validate_fixtures(bench.IMAGE)
        self.assertEqual(len(result), 3)
        self.assertEqual(len(seen), 6)
        for i, task in enumerate(bench.TASKS):
            self.assertEqual(seen[2*i][:2], (task["reference"],task["tests"]))
        with patch.object(bench, "grade_python", return_value={"passed": True, "tests_run": 0}):
            with self.assertRaises(ValueError): bench.validate_fixtures(bench.IMAGE)

    def test_generated_source_is_never_host_executed_and_hidden_tests_not_prompted(self):
        task = bench.TASKS[0]
        candidate = "raise RuntimeError('host must not execute this')"
        selected = {"requested": bench.strategies.BASELINE, "selection": {}, "selection_ms": 1,
                    "jev_callback_attempts": 0, "jev_ms": None}
        with patch.object(bench.strategies, "trial", return_value=selected) as select, \
                patch.object(bench.strategies, "native", return_value={"status": "completed", "answer": {"source": candidate}}) as native, \
                patch.object(bench, "grade_python", return_value={"passed": False, "status": "failed"}) as grade:
            result = bench.code_trial(task, "no_router_parent_baseline", 0, "/fixture/claude", None, bench.IMAGE)
        self.assertTrue(select.call_args.kwargs["strategy_only"])
        self.assertIn(task["contract"], native.call_args.args[2])
        self.assertNotIn(task["tests"], native.call_args.args[2])
        self.assertNotIn(task["reference"], native.call_args.args[2])
        grade.assert_called_once_with(candidate,task["tests"],image=bench.IMAGE)
        self.assertFalse(result["oracle_success"])
        self.assertIsNone(result["human_rework"])

    def test_no_candidate_failure_and_invalid_source_are_not_dropped(self):
        selected = {"requested": bench.strategies.BASELINE}
        for execution in ({"status": "timeout"}, {"status": "completed", "answer": {"source": "invalid"}}):
            with patch.object(bench.strategies, "trial", return_value=selected), \
                    patch.object(bench.strategies, "native", return_value=execution), \
                    patch.object(bench, "grade_python", side_effect=ValueError("invalid_source")):
                result = bench.code_trial(bench.TASKS[0], "A", 0, "/fixture", None, bench.IMAGE)
            self.assertFalse(result["oracle_success"])
            self.assertIn(result["grading"]["status"], ("no_candidate", "invalid_source"))
            self.assertEqual(result["orchestrator_retries"], 0)

    def test_candidate_cannot_pass_with_missing_frozen_test_methods(self):
        with patch.object(bench.strategies, "trial", return_value={"requested": bench.strategies.BASELINE}), \
                patch.object(bench.strategies, "native", return_value={"status": "completed", "answer": {"source": "fixture"}}), \
                patch.object(bench, "grade_python", return_value={"passed": True, "tests_run": 1, "cleanup_verified": True}):
            result = bench.code_trial(bench.TASKS[0], "A", 0, "/fixture", None, bench.IMAGE)
        self.assertFalse(result["oracle_success"])
        self.assertEqual(result["grading"]["status"], "test_count_or_cleanup_mismatch")


if __name__ == "__main__":
    unittest.main()

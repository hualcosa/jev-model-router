"""Offline host-side contract tests; generated candidates execute only in Docker."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "code_grader", Path(__file__).resolve().parents[1] / "scripts/spikes/code_grader.py")
grader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(grader)
IMAGE = "sha256:" + "a" * 64


def record(**updates):
    counts = dict(tests_run=1, failures=0, errors=0, skipped=0)
    counts.update(updates)
    return (grader._MARKER + json.dumps(counts) + "\n").encode()


class CodeGraderTests(unittest.TestCase):
    def test_rejects_mutable_image_and_oversized_input_before_docker(self):
        with patch.object(grader, "_capture") as capture:
            for image in ("python:latest", "sha256:bad", IMAGE + "\n", None):
                with self.assertRaises(ValueError):
                    grader.grade_python("", "", image=image)
            for source, tests in (("x" * 65537, ""), ("", "é" * 32769)):
                with self.assertRaises(ValueError):
                    grader.grade_python(source, tests, image=IMAGE)
            for timeout in (0, -1, 61, float("nan"), float("inf"), True):
                with self.assertRaises(ValueError):
                    grader.grade_python("", "", image=IMAGE, timeout_seconds=timeout)
            capture.assert_not_called()

    def test_fixed_boundary_and_bundle_only_readonly_mount(self):
        commands = []
        def capture(command, timeout, *args):
            commands.append(command)
            if command[1] == "run":
                mount = command[command.index("--mount") + 1]
                directory = Path(mount.split("source=")[1].split(",")[0])
                self.assertEqual({p.name for p in directory.iterdir()},
                                 {"solution.py", "trusted_tests.py", "grader.py"})
                self.assertEqual((directory / "solution.py").read_text(), "raise RuntimeError('never on host')")
                self.assertTrue(mount.endswith("target=/bundle,readonly"))
                return 0, record(), b"sensitive generated stderr", None, 200
            return 0, b"", b"", None, 0
        with patch.object(grader, "_capture", side_effect=capture):
            result = grader.grade_python("raise RuntimeError('never on host')", "trusted", image=IMAGE)
        run = commands[0]
        for flag in ("--pull=never", "--log-driver", "--read-only", "--cap-drop", "--security-opt",
                     "--network", "--user", "--pids-limit", "--memory", "--cpus", "--tmpfs"):
            self.assertIn(flag, run)
        self.assertEqual(run[run.index("--network")+1], "none")
        self.assertEqual(run[run.index("--user")+1], "65534:65534")
        self.assertEqual(run[-4:], [IMAGE, "-I", "-B", "/bundle/grader.py"])
        self.assertEqual(run.count("--mount"), 1)
        self.assertNotIn("--env", run)
        self.assertTrue(result["passed"])
        self.assertTrue(result["cleanup_verified"])
        self.assertNotIn("sensitive", json.dumps(result))
        self.assertEqual(commands[1][1:3], ["rm", "--force"])
        self.assertEqual(commands[2][1:4], ["ps", "--all", "--quiet"])

    def test_outcomes_and_cleanup_after_client_exit(self):
        cases = [(0, record(), None, "passed"),
                 (1, record(failures=1), None, "failed"),
                 (0, record(skipped=1), None, "failed"),
                 (0, record(tests_run=0), None, "failed"),
                 (0, b"not a result", None, "invalid_result"),
                 (0, record()+record(), None, "invalid_result"),
                 (125, b"daemon error", None, "runner_error"),
                 (-9, b"", "timeout", "timeout"),
                 (-9, b"", "output_limit", "output_limit")]
        for code, out, reason, status in cases:
            with self.subTest(status=status), patch.object(grader, "_capture", side_effect=[
                (code, out, b"", reason, len(out)), (0, b"", b"", None, 0),
                (0, b"", b"", None, 0)]):
                result = grader.grade_python("candidate", "trusted", image=IMAGE)
                self.assertEqual(result["status"], status)
                self.assertTrue(result["cleanup_verified"])

    def test_cleanup_failure_fails_closed(self):
        with patch.object(grader, "_capture", side_effect=[
            (0, record(), b"", None, 100), (1, b"", b"", None, 0),
            (0, b"container-still-present", b"", None, 1)]):
            result = grader.grade_python("", "", image=IMAGE)
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "cleanup_error")

    def test_capture_limits_and_timeouts_trusted_host_helper(self):
        # These are fixed host test helpers, never model-generated source.
        result = grader._capture([sys.executable, "-I", "-c", "print('x'*100000)"], 2, 1024)
        self.assertEqual(result[3], "output_limit")
        self.assertLessEqual(len(result[1]) + len(result[2]), 1024)
        result = grader._capture([sys.executable, "-I", "-c", "import time; time.sleep(5)"], .05)
        self.assertEqual(result[3], "timeout")

    def test_counts_reject_untrusted_shape(self):
        for value in (b'{}', b'{"tests_run": true}', b'[]', b'null', b'broken'):
            self.assertIsNone(grader._counts(grader._MARKER.encode() + value))


if __name__ == "__main__":
    unittest.main()

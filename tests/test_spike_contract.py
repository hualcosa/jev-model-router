"""Safety/contract tests for the P0 Jev audit command; no service calls."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.spikes import jev_contract


class JevSpikeSafetyTests(unittest.TestCase):
    def test_private_key_file_loaded_without_shell_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jev.env"
            path.write_text("TYPESAFE_API_KEY=synthetic-$(never-execute)\n")
            path.chmod(0o600)
            self.assertEqual(jev_contract.load_private_key(path), "synthetic-$(never-execute)")

    def test_unsafe_or_extra_assignments_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jev.env"
            path.write_text("TYPESAFE_API_KEY=synthetic\nOTHER=not-allowed\n")
            path.chmod(0o600)
            with self.assertRaises(ValueError):
                jev_contract.load_private_key(path)
            path.write_text("TYPESAFE_API_KEY=synthetic\n")
            path.chmod(0o644)
            if os.name == "posix":
                with self.assertRaises(ValueError):
                    jev_contract.load_private_key(path)

    @unittest.skipUnless(os.name == "posix", "POSIX symlink safety")
    def test_symlink_credential_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "secret"
            path.write_text("TYPESAFE_API_KEY=synthetic\n")
            path.chmod(0o600)
            link = Path(directory) / "jev.env"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                jev_contract.load_private_key(link)

    def test_live_requires_key_before_sdk_or_network(self):
        with patch.dict(os.environ, {}, clear=True):
            record, code = jev_contract.run(live=True)
        self.assertEqual(code, 2)
        self.assertEqual(record["status"], "blocked_missing_key")
        self.assertFalse(record["network_request"])

    def test_cli_help_needs_no_sdk_or_key(self):
        result = subprocess.run(
            [sys.executable, str(Path(jev_contract.__file__)), "--help"],
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--live-synthetic", result.stdout)

    def test_missing_key_report_private_and_no_task_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            env = os.environ.copy()
            env.pop("TYPESAFE_API_KEY", None)
            result = subprocess.run(
                [sys.executable, str(Path(jev_contract.__file__)),
                 "--live-synthetic", "--output", str(output)],
                capture_output=True, text=True, env=env, timeout=5)
            self.assertEqual(result.returncode, 2)
            record = json.loads(output.read_text())
            self.assertFalse(record["network_request"])
            self.assertNotIn(jev_contract.SYNTHETIC_TASK, output.read_text())
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(importlib.util.find_spec("typesafe_sdk"), "optional SDK not installed")
    def test_offline_mock_uses_sdk_without_network(self):
        record, code = jev_contract.run()
        self.assertEqual(code, 0, record)
        self.assertFalse(record["network_request"])
        self.assertEqual(record["evidence"], "official_sdk_mock_contract_only")
        self.assertEqual(record["request_count"], 1)
        self.assertEqual(record["selected_tier"], "T0")


if __name__ == "__main__":
    unittest.main()

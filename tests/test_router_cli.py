import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from router_core.cli import main, preflight
from router_core.config import merge_config_layers
from router_core.contracts import ProviderResult, ProviderStatus, TaskRequirements
from router_core.native import bootstrap_profile
from router_core.profiles import read_profile
from router_core.privacy import (Consent, PrivacyError, SYNTHETIC_SMOKE,
                                 build_task_description, preview_task_description)


class CLITests(unittest.TestCase):
    def config(self, **kwargs):
        return merge_config_layers({"mode": "warn", **kwargs}, {})

    def profile(self):
        return bootstrap_profile("claude", "cli", "2.1.303")

    def test_preview_never_grants_outbound_consent(self):
        text = "Review auth API_KEY=private-secret"
        preview = preview_task_description(text)
        self.assertNotIn("private-secret", preview.text)
        with self.assertRaises(PrivacyError):
            build_task_description(text)
        with self.assertRaises(PrivacyError):
            build_task_description(text, consent=Consent.SYNTHETIC)

    def test_local_commands_never_read_config_runtime_or_key(self):
        for command in ("preview", "preflight"):
            with self.subTest(command=command), patch("sys.stdin", io.TextIOWrapper(io.BytesIO(b"Review API_KEY=private-secret"))), contextlib.redirect_stdout(io.StringIO()) as output, patch("router_core.cli.load_config", side_effect=AssertionError()), patch("router_core.cli.runtime_version", side_effect=AssertionError()), patch("router_core.cli.load_private_key", side_effect=AssertionError()), patch("router_core.cli.JevClient", side_effect=AssertionError()):
                self.assertEqual(main([command]), 0)
                result = json.loads(output.getvalue())
                self.assertEqual(result["external_calls"], 0)
                self.assertNotIn("private-secret", output.getvalue())

    def test_preflight_recommends_without_running_or_selecting_worker(self):
        calls = []
        result = preflight(SYNTHETIC_SMOKE, runtime="claude", profile=self.profile(),
            config=self.config(consent={"synthetic_tasks": True}),
            classify=lambda p: calls.append(p.provider_state()) or ProviderResult(ProviderStatus.SUCCESS,
                TaskRequirements(0, 0, 0, .99, tier="T0", risk="low")))
        self.assertEqual(calls, [{"task_summary": SYNTHETIC_SMOKE}])
        self.assertEqual(result["decision"]["recommended_model"], "haiku")
        self.assertIsNone(result["decision"]["selected_model"])
        self.assertFalse(result["task_executed"])
        self.assertFalse(result["host_config_changed"])

    def test_zero_calls_for_missing_consent_nonfixture_disabled_or_unknown(self):
        calls = []
        for text, cfg, profile in (
            (SYNTHETIC_SMOKE, self.config(), self.profile()),
            ("real private task", self.config(consent={"synthetic_tasks": True}), self.profile()),
            (SYNTHETIC_SMOKE, merge_config_layers({}, {}), self.profile()),
            (SYNTHETIC_SMOKE, self.config(consent={"synthetic_tasks": True}), None)):
            preflight(text, runtime="claude", config=cfg, profile=profile,
                      classify=lambda p: calls.append(p))
        self.assertEqual(calls, [])

    def test_failures_sanitized_and_no_task_in_assessment_output(self):
        def broken(_):
            raise RuntimeError("hidden-secret")
        result = preflight(SYNTHETIC_SMOKE, runtime="claude", profile=self.profile(),
            config=self.config(consent={"synthetic_tasks": True}), classify=broken)
        self.assertEqual(result["decision"]["reason_code"], "classifier_unavailable")
        self.assertNotIn("hidden-secret", json.dumps(result))
        self.assertNotIn("imaginary", json.dumps(result))

    def test_launcher_stdin_bounds_encoding_and_nonexecution(self):
        script = str(Path(__file__).resolve().parents[1]/"scripts/router_cli.py")
        for value in (b"x"*100001, b"\xff", b"\x00"):
            result = subprocess.run([sys.executable, script, "preview"], input=value,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3, cwd="/tmp")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"], "error")
            self.assertFalse(result.stderr)
        result = subprocess.run([sys.executable, script, "preview"],
            input=b"Explain why `touch /tmp/router-preview-must-not-execute` is a command",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3, cwd="/tmp")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(Path("/tmp/router-preview-must-not-execute").exists())

    def test_preview_send_is_rejected_before_read(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main(["preview", "--send"])
        self.assertEqual(error.exception.code, 2)

    def test_cli_send_requires_existing_consent_before_key_or_provider(self):
        for consent in (False, True):
            with self.subTest(consent=consent), patch("sys.stdin", io.TextIOWrapper(io.BytesIO(SYNTHETIC_SMOKE.encode()))), contextlib.redirect_stdout(io.StringIO()) as output, patch("router_core.cli.load_config", return_value=self.config(consent={"synthetic_tasks": consent})), patch("router_core.cli.runtime_version", return_value="2.1.303"), patch("router_core.cli.load_private_key", return_value="fake-test-key") as key, patch("router_core.cli.JevClient") as client:
                client.return_value.classify.return_value = ProviderResult(ProviderStatus.SUCCESS,
                    TaskRequirements(0, 0, 0, .99, tier="T0", risk="low"))
                self.assertEqual(main(["preflight", "--send", "--runtime", "claude",
                    "--runtime-binary", "/imaginary/claude", "--key-file", "/imaginary/key"]), 0)
                self.assertEqual(key.call_count, int(consent))
                self.assertEqual(client.return_value.classify.call_count, int(consent))
                self.assertNotIn("fake-test-key", output.getvalue())
                self.assertNotIn("imaginary files", output.getvalue())

    def test_diagnostic_profile_write_is_explicit_private_and_never_activates_routing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root/"codex";binary.write_text("fixture");binary.chmod(0o700)
            profile_path = root/"private/profile.json"
            base = bootstrap_profile("codex", "cli", "0.163.0")
            inventory = {"catalog": json.loads(base.catalog.to_json()), "missing_desired_targets": ["terra:6"]}
            for write in (False, True):
                with contextlib.redirect_stdout(io.StringIO()) as output, patch("router_core.cli.runtime_version", return_value="0.163.0"), patch("router_core.cli.discover_codex_models", return_value=inventory), patch("router_core.cli.read_codex_hooks", return_value=[]), patch("router_core.cli.load_config", side_effect=AssertionError()), patch("router_core.cli.load_private_key", side_effect=AssertionError()), patch("router_core.cli.JevClient", side_effect=AssertionError()):
                    args = ["diagnose", "--runtime", "codex", "--runtime-binary", str(binary),
                            "--project", str(root), "--capability-profile", str(profile_path)]
                    self.assertEqual(main(args + (["--write-profile"] if write else [])), 0)
                    result = json.loads(output.getvalue())
                    self.assertEqual(result["status"], "advisory_only")
                    self.assertFalse(result["routing_enabled"])
                    self.assertEqual(result["inference_calls"], 0)
                    self.assertEqual(profile_path.exists(), write)
            self.assertEqual(read_profile(profile_path)["host_version"], "0.163.0")
            self.assertEqual(profile_path.stat().st_mode & 0o777, 0o600)

    def test_disabled_preflight_never_reads_even_explicit_profile(self):
        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(SYNTHETIC_SMOKE.encode()))), contextlib.redirect_stdout(io.StringIO()), patch("router_core.cli.load_config", return_value=merge_config_layers({}, {})), patch("router_core.cli.load_capability_profile", side_effect=AssertionError()), patch("router_core.cli.runtime_version", side_effect=AssertionError()):
            self.assertEqual(main(["preflight", "--send", "--runtime", "codex", "--runtime-binary", "/missing", "--capability-profile", "/missing"]), 0)


if __name__ == "__main__":
    unittest.main()

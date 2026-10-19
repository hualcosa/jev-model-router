"""Validate the SDK-required gate without recursively executing discovery."""
import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("offline_runner",
    Path(__file__).resolve().parents[1] / "scripts/run_offline_tests.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class OfflineRunnerTests(unittest.TestCase):
    def invoke(self, argv, *, sdk_version="0.7.5", success=True, skipped=()):
        result = Mock(skipped=skipped)
        result.wasSuccessful.return_value = success
        with patch.object(runner, "version", return_value=sdk_version), \
             patch.dict("sys.modules", {"typesafe_sdk": Mock(), "httpx2": Mock()}), \
             patch.object(runner.unittest.defaultTestLoader, "discover", return_value=[]) as discover, \
             patch.object(runner.unittest, "TextTestRunner") as execute, \
             contextlib.redirect_stderr(io.StringIO()):
            execute.return_value.run.return_value = result
            code = runner.main(argv)
            return code, discover.call_count, execute.return_value.run.call_count

    def test_pinned_sdk_required_and_no_skips_pass(self):
        self.assertEqual(self.invoke(["--require-sdk"]), (0, 1, 1))

    def test_wrong_sdk_fails_before_discovery(self):
        self.assertEqual(self.invoke(["--require-sdk"], sdk_version="0.0.0"), (2, 0, 0))

    def test_skipped_contract_or_failed_test_is_not_green(self):
        self.assertEqual(self.invoke(["--require-sdk"], skipped=[("contract", "absent")])[0], 1)
        self.assertEqual(self.invoke(["--require-sdk"], success=False)[0], 1)

    def test_dependency_free_mode_allows_optional_sdk_skips_but_not_failures(self):
        self.assertEqual(self.invoke([], skipped=[("contract", "absent")])[0], 0)
        self.assertEqual(self.invoke([], success=False)[0], 1)

    def test_missing_sdk_is_sanitized_and_prevents_discovery(self):
        with patch.object(runner, "version", side_effect=runner.PackageNotFoundError("private")), \
             patch.object(runner.unittest.defaultTestLoader, "discover") as discover, \
             contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(runner.main(["--require-sdk"]), 2)
            discover.assert_not_called()
            self.assertNotIn("private", error.getvalue())

    def test_installed_but_unimportable_transport_fails_before_discovery(self):
        with patch.object(runner, "version", return_value="0.7.5"), \
             patch.dict("sys.modules", {"typesafe_sdk": Mock(), "httpx2": None}), \
             patch.object(runner.unittest.defaultTestLoader, "discover") as discover, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(runner.main(["--require-sdk"]), 2)
            discover.assert_not_called()

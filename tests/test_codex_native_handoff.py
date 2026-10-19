import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import prepare_codex_native_test as handoff


class NativeHandoffTests(unittest.TestCase):
    def test_prepares_disabled_private_artifact_without_key_read_or_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/"new"
            root.mkdir(mode=0o700)
            missing_key = Path(directory)/"key-that-must-not-be-read.env"
            with patch.object(handoff.subprocess, "check_output", return_value=b"codex-cli 0.163.0\n") as version, \
                    patch.object(handoff.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as dependency, \
                    patch.object(handoff.tempfile, "mkdtemp", return_value=str(root)):
                result = handoff.prepare(python=sys.executable, binary=sys.executable, key_file=str(missing_key))
            self.assertFalse(result["installed"])
            self.assertFalse(result["trust_granted"])
            self.assertFalse(result["routing_enabled"])
            self.assertEqual(result["provider_calls"], 0)
            self.assertFalse(missing_key.exists())
            self.assertEqual(json.loads(Path(result["config"]).read_text())["mode"], "disabled")
            self.assertFalse(Path(result["profile"]).exists())
            self.assertFalse(Path(result["state"]).exists())
            self.assertEqual(version.call_args.args[0], [sys.executable, "--version"])
            self.assertEqual(dependency.call_count, 1)
            self.assertEqual(dependency.call_args.args[0][:3], [sys.executable,"-I","-c"])
            self.assertEqual((root/"HANDOFF.json").stat().st_mode & 0o777, 0o600)
            self.assertIn("/hooks", (root/"LEIA-ME.md").read_text())
            self.assertNotIn("bypass-hook-trust", (root/"LEIA-ME.md").read_text())
            hooks=json.loads((root/"marketplace/plugins/intelligent-agent-router/hooks/hooks.json").read_text())
            self.assertEqual(len(hooks["hooks"]),8)

    def test_unknown_runtime_or_missing_sdk_fails_before_creating_paths(self):
        for output, code in ((b"codex-cli 9.0.0",0),(b"codex-cli 0.163.0",1)):
            with patch.object(handoff.subprocess,"check_output",return_value=output), \
                    patch.object(handoff.subprocess,"run",return_value=subprocess.CompletedProcess([],code)), \
                    patch.object(handoff.tempfile,"mkdtemp") as create:
                with self.assertRaises(ValueError):
                    handoff.prepare(python=sys.executable,binary=sys.executable,key_file="/missing/key")
                create.assert_not_called()


if __name__ == "__main__":
    unittest.main()

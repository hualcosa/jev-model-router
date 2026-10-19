import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.spikes.codex_package_smoke import config_snapshot, _COMMAND_SHAPE_CHECK


class PackageSpikeTests(unittest.TestCase):
    def test_snapshot_reads_only_bounded_config_and_never_returns_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"config.toml").write_text("secret=synthetic_value")
            (root/"auth.json").write_text("never read auth")
            result = config_snapshot(root)
            self.assertEqual(result, {"config.toml": hashlib.sha256(b"secret=synthetic_value").hexdigest(), "hooks.json": None})
            self.assertNotIn("synthetic_value", str(result))

    def test_snapshot_rejects_symlink_not_following_credential_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"auth.json").write_text("never read auth")
            (root/"config.toml").symlink_to(root/"auth.json")
            with self.assertRaises(OSError):
                config_snapshot(root)

    def test_installed_shape_check_compiles_and_never_grants_trust(self):
        compile(_COMMAND_SHAPE_CHECK, "shape-check", "exec")
        self.assertIn("read_codex_hooks", _COMMAND_SHAPE_CHECK)
        self.assertIn("_own_command", _COMMAND_SHAPE_CHECK)
        self.assertNotIn("write_profile", _COMMAND_SHAPE_CHECK)
        self.assertNotIn("turn/start", _COMMAND_SHAPE_CHECK)


if __name__ == "__main__":
    unittest.main()

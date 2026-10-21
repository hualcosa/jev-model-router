"""Regression tests for public-doc checks, separate from legacy advisory parity."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("public_docs", Path(__file__).resolve().parents[1] / "scripts/check_public_docs.py")
docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(docs)


class PublicDocsTests(unittest.TestCase):
    def test_legacy_sync_targets_do_not_inject_taxonomy_into_product_readme(self):
        spec = importlib.util.spec_from_file_location("sync_docs", docs.ROOT / "scripts/sync_docs.py")
        sync = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sync)
        self.assertEqual(set(sync.TARGETS), {"prompt.md", "plugins/claude-model-router-hook/prompt.md"})
        self.assertEqual(sync._sync_text(sync._desired_block("canonical\n"), "canonical\n")[1], "in_sync")
        self.assertEqual(sync._sync_text(sync._desired_block("stale\n"), "canonical\n")[1], "drift")
        self.assertEqual(sync._sync_text("missing", "canonical\n")[1], "no_markers")

    def test_links_check_existence_private_boundary_anchors_and_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "README.md").write_text("# Intro\n")
            (root / "guide.md").write_text("# Disable and roll back\n")
            self.assertEqual(docs.local_link_errors(root, "README.md", "[ok](guide.md#disable-and-roll-back)"), [])
            for text in ("[bad](absent.md)", "[bad](guide.md#absent)", "[bad](../outside.md)", "[bad](specs/internal.md)"):
                with self.subTest(text=text):
                    self.assertTrue(docs.local_link_errors(root, "README.md", text))
            self.assertEqual(docs.local_link_errors(root, "README.md", "[web](https://example.com/none)"), [])

    def test_picture_sources_are_checked_and_html_images_need_alt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "README.md").write_text("# Intro\n")
            errors = docs.local_link_errors(root, "README.md", '<picture><source srcset="missing.svg"><img src="missing.png"></picture>')
            self.assertTrue(any("missing.svg" in e for e in errors))
            self.assertTrue(any("missing.png" in e for e in errors))
            self.assertTrue(any("text alternative" in e for e in errors))

    def test_check_fails_closed_on_missing_public_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            errors = docs.check(Path(temp))
            self.assertTrue(any("missing public document" in x for x in errors))
            self.assertTrue(any("missing public asset" in x for x in errors))
            self.assertTrue(any("demo evidence" in x for x in errors))

    def test_public_intake_uses_this_projects_security_and_safe_diagnostics(self):
        config = (docs.ROOT / ".github/ISSUE_TEMPLATE/config.yml").read_text()
        self.assertIn("https://github.com/hualcosa/jev-model-router/security/policy", config)
        self.assertNotIn("tzachbon", config)
        bug = (docs.ROOT / ".github/ISSUE_TEMPLATE/bug_report.md").read_text()
        self.assertIn("minimal synthetic reproducer", bug)
        self.assertNotIn("Paste the relevant lines", bug)
        pr = (docs.ROOT / ".github/PULL_REQUEST_TEMPLATE.md").read_text()
        self.assertNotIn("Installed locally with", pr)
        self.assertIn("impacted offline checks", pr)

    def test_anchor_duplicate_suffix_matches_github(self):
        self.assertEqual(docs.anchors("# Hello, World!\n## Hello, World!\n"), {"hello-world", "hello-world-1"})


if __name__ == "__main__":
    unittest.main()

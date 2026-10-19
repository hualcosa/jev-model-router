from dataclasses import replace
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch

from router_core.native import bootstrap_profile
from router_core.profiles import (ProfileError, ROOT, analyze_hooks, build_profile_document,
    load_capability_profile, read_profile, write_profile)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        self.binary = self.project/"codex"
        self.binary.write_text("#!/bin/sh\nexit 0\n")
        self.binary.chmod(0o700)
        self.path = self.project/"private/profile.json"
        self.base = bootstrap_profile("codex", "cli", "0.163.0")
        tokens = [sys.executable, str(ROOT/"scripts/router_hook.py"), "--runtime", "codex", "--surface", "cli",
                  "--runtime-binary", str(self.binary), "--project", str(self.project), "--capability-profile", str(self.path)]
        self.hook = dict(key="fixture:pre:0", eventName="preToolUse", enabled=True, trustStatus="trusted",
                         handlerType="command", **{"async": False}, matcher="^collaborationspawn_agent$", command=shlex.join(tokens))

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, hooks=None):
        return build_profile_document(runtime="codex", surface="cli", version="0.163.0", project=self.project,
            binary=str(self.binary), profile_path=self.path, catalog=self.base.catalog,
            hooks=[self.hook] if hooks is None else hooks, now=1000)

    def load(self, hooks=None, **kwargs):
        args = dict(runtime="codex", surface="cli", version="0.163.0", project=self.project,
                    binary=str(self.binary), now=1001, hooks=[self.hook] if hooks is None else hooks)
        args.update(kwargs)
        return load_capability_profile(self.path, **args)

    def test_private_roundtrip_live_verified_scope_and_only_measured_permission(self):
        doc, result = self.build()
        self.assertTrue(result["safe"])
        write_profile(self.path, doc)
        self.assertEqual(read_profile(self.path), doc)
        profile = self.load()
        self.assertTrue(profile.conflicts_checked)
        self.assertEqual(profile.safe_rewrite_permission_modes, frozenset({"bypassPermissions"}))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
        raw = self.path.read_text()
        self.assertNotIn(str(self.project), raw)
        self.assertNotIn(self.hook["command"], raw)

    def test_unknown_competing_untrusted_duplicate_or_async_hooks_disable_rewrite(self):
        cases = [[], [self.hook, {**self.hook, "key": "other", "command": "unknown command"}],
                 [{**self.hook, "trustStatus": "needsReview"}], [{**self.hook, "async": True}],
                 [self.hook, {**self.hook, "key": "duplicate"}],
                 [self.hook, {**self.hook, "key": "unknown-regex", "matcher": "(a+)+$", "command": "other"}]]
        for hooks in cases:
            with self.subTest(hooks=hooks):
                doc, result = self.build(hooks)
                self.assertFalse(result["safe"])
                write_profile(self.path, doc)
                loaded = self.load(hooks)
                self.assertFalse(loaded.conflicts_checked)
                self.assertFalse(loaded.safe_rewrite_permission_modes)

    def test_nonmatching_hooks_do_not_require_undocumented_merge_order(self):
        for matcher in ("^mcp__engram__mem_.*$", "Edit|Write|apply_patch", "Bash",
                        "mcp__engram__mem_*|mcp__plugin_engram_engram__mem_*"):
            hooks = [self.hook, {**self.hook, "key": matcher, "matcher": matcher, "command": "unrelated"}]
            self.assertTrue(self.build(hooks)[1]["safe"])

    def test_terminal_literal_star_preserves_regex_search_and_unknown_guards(self):
        # '*' is a regex quantifier, not a glob: k may appear zero times.
        for matcher in ("Task*", "spawn_agent*", "^spawn_agent*$", "a*a*", "*", "x**"):
            with self.subTest(matcher=matcher):
                hook = {**self.hook, "key": "quantified", "matcher": matcher, "command": "other"}
                self.assertFalse(self.build([self.hook, hook])[1]["safe"])

    def test_regex_search_wildcards_prefixes_and_unknown_syntax_overlap(self):
        for matcher in ("spawn.agent", "spawn", "^collaboration", r"^collaboration\.spawn_agent$",
                        "(?:spawn_agent|Task)", "(a+)+$", "[s]pawn_agent", "(?i)task"):
            with self.subTest(matcher=matcher):
                competitor = {**self.hook, "key": "competitor", "matcher": matcher, "command": "unrelated"}
                self.assertFalse(self.build([self.hook, competitor])[1]["safe"])

    def test_shell_expansion_operators_and_relative_optional_paths_are_not_own(self):
        for suffix in (' --key-file "$(printf ignored)"', ' --key-file "`printf ignored`"',
                       ' --key-file "$HOME/key"', ' > /tmp/output', ' | cat', '; true',
                       ' && true', '\ntrue', ' --key-file relative.env'):
            with self.subTest(suffix=suffix):
                hook = {**self.hook, "command": self.hook["command"] + suffix}
                self.assertFalse(self.build([hook])[1]["safe"])

    def test_shell_quoted_path_with_spaces_is_supported(self):
        hook = {**self.hook, "command": self.hook["command"] + " --key-file " + shlex.quote(str(self.project/"key with spaces.env"))}
        self.assertTrue(self.build([hook])[1]["safe"])

    def test_only_exact_source_bound_unbraced_plugin_root_token_is_own(self):
        tokens = shlex.split(self.hook["command"])
        command = shlex.quote(tokens[0]) + ' "$PLUGIN_ROOT/scripts/router_hook.py" ' + shlex.join(tokens[2:])
        hook = {**self.hook, "command": command, "source": "plugin", "pluginId": "intelligent-agent-router@fixture",
                "sourcePath": str(ROOT/"hooks/hooks.json")}
        self.assertTrue(self.build([hook])[1]["safe"])
        for patch in ({"source": "project"}, {"sourcePath": str(self.project/"hooks/hooks.json")},
                      {"pluginId": "other-plugin@fixture"}, {"command": command.replace("$PLUGIN_ROOT", "${PLUGIN_ROOT}")},
                      {"command": command + ' --key-file "$(printf ignored)"'}):
            self.assertFalse(self.build([{**hook, **patch}])[1]["safe"])

    def test_any_hook_inventory_change_invalidates_existing_binding(self):
        write_profile(self.path, self.build()[0])
        with self.assertRaisesRegex(ProfileError, "hook_inventory_changed"):
            self.load([{**self.hook, "currentHash": "new-state"}])

    def test_scope_binary_code_and_expiry_changes_reject_stale_authority(self):
        write_profile(self.path, self.build()[0])
        for changes in ({"runtime": "claude"}, {"surface": "desktop"}, {"version": "unknown"},
                        {"project": self.project/"other"}, {"now": 87400}, {"now": 999}):
            with self.subTest(changes=changes), self.assertRaises(ProfileError):
                self.load(**changes)
        with patch("router_core.profiles.implementation_digest", return_value="f"*64), self.assertRaises(ProfileError):
            self.load()
        self.binary.write_text("changed binary identity")
        with self.assertRaises(ProfileError):
            self.load()

    def test_source_alias_cannot_reuse_reviewed_hook_identity(self):
        write_profile(self.path, self.build()[0])
        alias = self.project/"alias"
        alias.symlink_to(self.project, target_is_directory=True)
        with self.assertRaises(ProfileError):
            self.load(project=alias)

    def test_missing_read_has_no_install_side_effect(self):
        with self.assertRaises(ProfileError):
            read_profile(self.path)
        self.assertFalse(self.path.parent.exists())

    def test_refuses_symlink_hardlink_fifo_and_unsafe_mode(self):
        doc = self.build()[0]
        write_profile(self.path, doc)
        self.path.chmod(0o644)
        with self.assertRaises(ProfileError):
            read_profile(self.path)
        self.path.chmod(0o600)
        hard = self.path.parent/"hard.json";os.link(self.path, hard)
        with self.assertRaises(ProfileError):
            read_profile(self.path)
        hard.unlink()
        link = self.path.parent/"link.json";link.symlink_to(self.path)
        with self.assertRaises(ProfileError):
            read_profile(link)
        fifo = self.path.parent/"fifo";os.mkfifo(fifo, 0o600)
        with self.assertRaises(ProfileError):
            read_profile(fifo)

    def test_cannot_grant_permissions_using_json_booleans_or_wrong_catalog_scope(self):
        doc = self.build()[0]
        for key, value in (("conflicts_checked", True), ("safe_rewrite_permission_modes", ["default"])):
            with self.assertRaises(ProfileError):
                write_profile(self.path, {**doc, key: value})
        bad = json.loads(json.dumps(doc));bad["catalog"]["entries"][0]["host_version"] = "unknown"
        with self.assertRaises(ProfileError):
            write_profile(self.path, bad)
        bad = json.loads(json.dumps(doc));bad["catalog"]["entries"][0]["runtime_model_id"] = "gpt-6-astra"
        with self.assertRaises(ProfileError):
            write_profile(self.path, bad)

    def test_unrelated_existing_key_file_never_overwritten(self):
        self.path.parent.mkdir(mode=0o700)
        self.path.write_text('TYPESAFE_API_KEY=private-secret\n');self.path.chmod(0o600)
        with self.assertRaises(ProfileError):
            write_profile(self.path, self.build()[0])
        self.assertEqual(self.path.read_text(), 'TYPESAFE_API_KEY=private-secret\n')

    def test_production_loader_queries_live_public_inventory_not_saved_safe_boolean(self):
        write_profile(self.path, self.build()[0])
        with patch("router_core.profiles.read_codex_hooks", return_value=[self.hook]) as live:
            result = load_capability_profile(self.path, runtime="codex", surface="cli", version="0.163.0",
                project=self.project, binary=str(self.binary), now=1001)
            self.assertTrue(result.conflicts_checked)
            live.assert_called_once()


if __name__ == "__main__":
    unittest.main()

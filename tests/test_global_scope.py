from dataclasses import replace
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch

from router_core.global_scope import scope_key, profile_path, state_path, codex_profile, scoped_config
from router_core.packaging import Bindings, build_codex_package
from router_core.profiles import ROOT, analyze_hooks, ProfileError


class GlobalScopeTests(unittest.TestCase):
    def test_parent_revocation_applies_to_nested_workdir_and_cannot_be_reenabled(self):
        from router_core.config import ConfigError
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); child=root/"src"; child.mkdir()
            g=root/"global.json";g.write_text(json.dumps({"mode":"auto_workers","consent":{"real_tasks":True}}))
            p=root/".intelligent-agent-router.json";p.write_text(json.dumps({"mode":"disabled","consent":{"real_tasks":False}}))
            cfg=scoped_config(g,child)
            self.assertEqual(cfg.mode,"disabled");self.assertFalse(cfg.consent.real_tasks)
            (child/".intelligent-agent-router.json").write_text(json.dumps({"mode":"auto_workers"}))
            with self.assertRaises(ConfigError): scoped_config(g,child)

    def test_projects_and_lexical_aliases_have_different_authority_and_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            a = root / "a"; a.mkdir()
            alias = root / "alias"; alias.symlink_to(a, target_is_directory=True)
            for other in (root / "b", alias):
                self.assertNotEqual(scope_key(a), scope_key(other))
                self.assertNotEqual(profile_path(root, a), profile_path(root, other))
                self.assertNotEqual(state_path(root, a), state_path(root, other))
            self.assertEqual(profile_path(root, a).parent, root)
            self.assertEqual(len(scope_key(a)), 64)

    def test_global_own_hook_requires_exact_installed_source_and_scoped_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp).resolve()
            profiles = project / "profiles"
            args = ["--scope", "global", "--runtime", "codex", "--surface", "cli",
                "--runtime-binary", sys.executable, "--capability-profile", str(profiles)]
            command = shlex.quote(sys.executable) + ' "$PLUGIN_ROOT/scripts/router_hook.py" ' + shlex.join(args)
            hook = dict(key="global", eventName="preToolUse", enabled=True, trustStatus="trusted",
                handlerType="command", **{"async": False}, matcher="^spawn_agent$", command=command,
                source="plugin", pluginId="intelligent-agent-router@global", sourcePath=str(ROOT/"hooks/hooks.json"))
            def check(hook=hook, path=None):
                return analyze_hooks([hook], runtime="codex", surface="cli", project=project,
                    binary=sys.executable, profile_path=path or profile_path(profiles, project))["safe"]
            self.assertTrue(check())
            for change in ({"source":"user"}, {"pluginId":"other@global"},
                           {"sourcePath":str(project/"hooks.json")},
                           {"command":command+" --project "+str(project)},
                           {"command":command.replace("--scope global", "--scope unsupported")}):
                self.assertFalse(check({**hook, **change}))
            self.assertFalse(check(path=profile_path(profiles, project/"other")))

    def test_no_refresh_means_no_discovery_or_write_for_missing_stale_authority(self):
        with patch("router_core.profiles.load_capability_profile", side_effect=ProfileError("stale")), \
             patch("router_core.inventory.discover_codex_models") as discover, \
             patch("router_core.profiles.write_profile") as write:
            with self.assertRaises(ProfileError):
                codex_profile("/private/profiles", project="/project", binary=sys.executable,
                    surface="cli", version="0.163.0")
            discover.assert_not_called(); write.assert_not_called()

    def test_refresh_uses_live_native_inventory_and_does_not_infer_safe_authority(self):
        with patch("router_core.profiles.load_capability_profile", side_effect=[ProfileError("stale"), "loaded"]), \
             patch("router_core.inventory.discover_codex_models", return_value={"catalog":{"entries":[]}}) as discover, \
             patch("router_core.inventory.read_codex_hooks", return_value=[{"untrusted":True}]) as hooks, \
             patch("router_core.catalog.CatalogRegistry.from_json", return_value="catalog"), \
             patch("router_core.profiles.build_profile_document", return_value=({"doc":True},{"safe":False})) as build, \
             patch("router_core.profiles.write_profile") as write:
            result=codex_profile("/private/profiles", project="/project", binary=sys.executable,
                surface="cli", version="0.163.0", refresh=True)
            self.assertEqual(result,"loaded")
            self.assertEqual(build.call_args.kwargs["hooks"],[{"untrusted":True}])
            self.assertEqual(write.call_args.args[0],profile_path("/private/profiles","/project"))
            discover.assert_called_once(); hooks.assert_called_once()

    def test_global_package_has_dynamic_scope_not_a_static_project_and_distinct_marketplace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            b=Bindings(str(root),sys.executable,sys.executable,str(root/"config.json"),
                str(root/"state"),str(root/"profiles"),global_scope=True)
            result=build_codex_package(root/"global",b)
            static=build_codex_package(root/"static",replace(b,global_scope=False))
            self.assertNotEqual(result["marketplace"],static["marketplace"])
            plugin=root/"global/plugins/intelligent-agent-router"
            hooks=json.loads((plugin/"hooks/hooks.json").read_text())["hooks"]
            self.assertEqual(hooks["SessionStart"][0]["hooks"][0]["timeout"],30)
            for entries in hooks.values():
                command=entries[0]["hooks"][0]["command"]
                self.assertIn("--scope global",command)
                self.assertNotIn("--project",command)
            self.assertIn("--scope",(plugin/".mcp.json").read_text())


if __name__=="__main__":
    unittest.main()

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from router_core.packaging import Bindings, NAME, ROOT, PackageError, build_codex_package, build_claude_package


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.output = self.root/"package with spaces"
        self.bindings = Bindings(str(self.root), sys.executable, sys.executable,
            str(self.root/"not-created/config.json"), str(self.root/"not-created/state"),
            str(self.root/"not-created/profile.json"), str(self.root/"not-created/jev.env"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_global_claude_bundles_native_post_classic_mod_without_activation(self):
        bindings = replace(self.bindings, capability_profile=None, global_scope=True)
        result = build_claude_package(self.output, bindings)
        plugin = self.output/"plugins"/NAME
        document = json.loads((plugin/"hooks/hooks.json").read_text())
        self.assertEqual(document["modules"], ["./register.js"])
        self.assertTrue((plugin/"hooks/eligibility.js").is_file())
        self.assertTrue((plugin/"scripts/router_claude_mod.py").is_file())
        self.assertIn("$.plugin.root", (plugin/"hooks/register.js").read_text())
        self.assertNotIn(str(ROOT), (plugin/"hooks/bindings.js").read_text())
        self.assertFalse(result["routing_enabled"])
        self.assertFalse((self.root/"not-created").exists())

    def test_claude_exec_form_contains_only_new_core_hooks_no_autoswitch(self):
        bindings = replace(self.bindings, capability_profile=None)
        result = build_claude_package(self.output, bindings)
        self.assertEqual(result["runtime"], "claude")
        self.assertFalse(result["routing_enabled"])
        plugin = self.output / "plugins" / NAME
        self.assertTrue((plugin / ".claude-plugin/plugin.json").is_file())
        self.assertFalse((plugin / ".codex-plugin").exists())
        self.assertFalse((plugin / ".mcp.json").exists())
        manifest = json.loads((plugin / ".claude-plugin/plugin.json").read_text())
        self.assertNotIn("hooks", manifest)  # native default loads hooks.json once
        hooks = json.loads((plugin / "hooks/hooks.json").read_text())["hooks"]
        self.assertEqual(len(hooks), 12)
        self.assertEqual(hooks["PreToolUse"][0]["matcher"], "^(Agent|Task)$")
        for entries in hooks.values():
            handler = entries[0]["hooks"][0]
            self.assertEqual(handler["command"], bindings.python)
            self.assertEqual(handler["args"][0], "${CLAUDE_PLUGIN_ROOT}/scripts/router_hook.py")
            self.assertEqual(handler["args"][-2:], ["--key-file", bindings.key_file])
            self.assertIn("claude", handler["args"])
            self.assertEqual(handler["onFailure"], "continue")
            self.assertNotIn("--capability-profile", handler["args"])
        self.assertFalse(list(plugin.rglob("session_init.py")))
        self.assertFalse(list(plugin.rglob("user_prompt_submit.py")))
        marketplace = json.loads((self.output / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(marketplace["plugins"][0]["source"], "./plugins/" + NAME)

    def test_claude_relocated_exec_argv_is_safe_and_disabled_by_default(self):
        build_claude_package(self.output, replace(self.bindings, capability_profile=None))
        relocated = self.root / 'claude " $(touch SHOULD_NOT_EXIST) `touch ALSO_NOT_EXIST`'
        shutil.copytree(self.output / "plugins" / NAME, relocated)
        shutil.rmtree(self.output)
        handler = json.loads((relocated / "hooks/hooks.json").read_text())["hooks"]["SessionStart"][0]["hooks"][0]
        argv = [handler["command"], *[a.replace("${CLAUDE_PLUGIN_ROOT}", str(relocated)) for a in handler["args"]]]
        result = subprocess.run(argv, input=b'{}', capture_output=True, cwd=self.root, timeout=3)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        self.assertFalse((self.root / "SHOULD_NOT_EXIST").exists())
        self.assertFalse((self.root / "ALSO_NOT_EXIST").exists())
        self.assertFalse((self.root / "not-created").exists())

    def test_runtime_specific_profile_authority_is_not_silently_ignored(self):
        with self.assertRaisesRegex(PackageError, "claude_capability_profile_not_supported"):
            build_claude_package(self.output, self.bindings)
        with self.assertRaisesRegex(PackageError, "codex_capability_profile_required"):
            build_codex_package(self.output, replace(self.bindings, capability_profile=None))
        self.assertFalse(self.output.exists())

    def test_private_self_contained_artifact_hashes_and_no_activation(self):
        result = build_codex_package(self.output, self.bindings)
        self.assertEqual(result["status"], "built_not_installed")
        self.assertFalse(result["routing_enabled"])
        self.assertFalse(result["trust_granted"])
        self.assertFalse((self.root/"not-created").exists())
        info = json.loads((self.output/"BUILD.json").read_text())
        for name, digest in info["sha256"].items():
            self.assertEqual(hashlib.sha256((self.output/name).read_bytes()).hexdigest(), digest)
        for path in self.output.rglob("*"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700 if path.is_dir() else 0o600)
        plugin = self.output/"plugins"/NAME
        self.assertTrue((plugin/"router_core/_jev_worker.py").is_file())
        self.assertTrue((plugin/"router_core/telemetry.py").is_file())
        self.assertTrue((plugin/"router_core/explain.py").is_file())
        hooks = json.loads((plugin/"hooks/hooks.json").read_text())["hooks"]
        self.assertEqual(set(hooks), {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
                                     "SubagentStart", "SubagentStop", "PostCompact", "SessionEnd"})
        self.assertEqual(hooks["PreToolUse"][0]["matcher"], hooks["PostToolUse"][0]["matcher"])
        self.assertTrue((plugin/"LICENSE").is_file())
        self.assertFalse(list(plugin.rglob("*.pyc")))
        manifest = json.loads((plugin/".codex-plugin/plugin.json").read_text())
        self.assertEqual(manifest["hooks"], "./hooks/hooks.json")
        self.assertEqual(manifest["mcpServers"], "./.mcp.json")
        marketplace = json.loads((self.output/".agents/plugins/marketplace.json").read_text())
        self.assertEqual(marketplace["plugins"][0]["source"]["path"], "./plugins/"+NAME)

    def test_relocated_hook_is_disabled_without_runtime_key_state_or_checkout(self):
        build_codex_package(self.output, self.bindings)
        relocated = self.root/"relocated plugin with spaces"
        shutil.copytree(self.output/"plugins"/NAME, relocated)
        shutil.rmtree(self.output)
        hooks = json.loads((relocated/"hooks/hooks.json").read_text())["hooks"]
        command = hooks["UserPromptSubmit"][0]["hooks"][0]["command"]
        proc = subprocess.run(command, shell=True, env={**os.environ, "PLUGIN_ROOT": str(relocated)},
            cwd=self.root, input=b'{"private":"ignored"}', stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, b"", b""))
        self.assertFalse((self.root/"not-created").exists())

    def test_shell_metacharacters_in_plugin_root_are_literal_not_executed(self):
        build_codex_package(self.output, self.bindings)
        # Harmless sentinel test: malicious-looking PATH BYTES must never be
        # reparsed as substitutions. No provider/runtime is called (disabled).
        relocated = self.root/'plugin " $(touch SHOULD_NOT_EXIST) `touch ALSO_NOT_EXIST`'
        shutil.copytree(self.output/"plugins"/NAME, relocated)
        command = json.loads((relocated/"hooks/hooks.json").read_text())["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        self.assertNotIn("${PLUGIN_ROOT}", command)
        self.assertIn('"$PLUGIN_ROOT/scripts/router_hook.py"', command)
        proc = subprocess.run(command, shell=True, env={**os.environ, "PLUGIN_ROOT": str(relocated)},
            cwd=self.root, input=b'{}', capture_output=True, timeout=3)
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, b"", b""))
        self.assertFalse((self.root/"SHOULD_NOT_EXIST").exists())
        self.assertFalse((self.root/"ALSO_NOT_EXIST").exists())

    def test_relocated_offline_explain_creates_no_state_or_import_cache(self):
        build_codex_package(self.output,self.bindings)
        relocated=self.root/"offline relocated plugin"
        shutil.copytree(self.output/"plugins"/NAME,relocated)
        shutil.rmtree(self.output)
        before={str(p.relative_to(relocated)):(p.stat().st_mtime_ns,p.read_bytes())
                for p in relocated.rglob("*") if p.is_file()}
        state=self.root/"explain-state-must-not-exist"
        result=subprocess.run([sys.executable,str(relocated/"scripts/router_cli.py"),"explain",
            "--state-dir",str(state),"--scope-hash","a"*64],
            stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=3,cwd=self.root)
        self.assertEqual(result.returncode,0)
        self.assertFalse(result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"],"no_records")
        self.assertFalse(state.exists())
        self.assertFalse(list(relocated.rglob("__pycache__")))
        self.assertEqual(before,{str(p.relative_to(relocated)):(p.stat().st_mtime_ns,p.read_bytes())
                for p in relocated.rglob("*") if p.is_file()})

    def test_relocated_packaged_mcp_initializes_but_does_not_enable_routing(self):
        build_codex_package(self.output, self.bindings)
        plugin = self.output/"plugins"/NAME
        server = json.loads((plugin/".mcp.json").read_text())["mcpServers"]["intelligent_router"]
        args = [a.replace("${PLUGIN_ROOT}", str(plugin)) for a in server["args"]]
        requests = [dict(jsonrpc="2.0", id=1, method="initialize", params={"protocolVersion": "2025-11-25"}),
                    dict(jsonrpc="2.0", id=2, method="tools/call", params={"name": "prepare_task",
                         "arguments": {"session_id": "test", "task_id": "test", "task_text": "synthetic"}})]
        proc = subprocess.run([server["command"], *args], input="".join(json.dumps(r)+"\n" for r in requests),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=self.root, timeout=3)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, "")
        rows = [json.loads(line) for line in proc.stdout.splitlines()]
        answer = json.loads(rows[1]["result"]["content"][0]["text"])
        self.assertEqual(answer, {"ok": False, "reason": "disabled_or_unsupported"})
        self.assertFalse((self.root/"not-created").exists())

    def test_existing_file_folder_or_symlink_never_replaced(self):
        for kind in ("file", "folder", "symlink"):
            output = self.root/kind
            if kind == "file":
                output.write_text("keep")
            elif kind == "folder":
                output.mkdir(); (output/"keep").write_text("keep")
            else:
                output.symlink_to(self.root/"missing")
            with self.assertRaises(PackageError):
                build_codex_package(output, self.bindings)
            self.assertTrue(output.exists() or output.is_symlink())
            if kind == "file":
                self.assertEqual(output.read_text(), "keep")

    def test_invalid_paths_surface_and_writable_executables_rejected(self):
        for patch in ({"project": "relative"}, {"surface": "web"}, {"key_file": "/key\nsecret"}):
            with self.assertRaises(PackageError):
                replace(self.bindings, **patch)
        binary = self.root/"unsafe-python"
        binary.write_text("#!/bin/sh\nexit 0\n"); binary.chmod(0o777)
        with self.assertRaises(PackageError):
            replace(self.bindings, python=str(binary))

    def test_native_placeholder_bytes_in_any_explicit_binding_are_rejected(self):
        for field in ("project", "python", "runtime_binary", "global_config", "state_dir", "capability_profile", "key_file"):
            for placeholder in ("${PLUGIN_ROOT}", "${PLUGIN_DATA}", "${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_PLUGIN_DATA}"):
                with self.subTest(field=field, placeholder=placeholder), self.assertRaises(PackageError):
                    replace(self.bindings, **{field: "/literal/"+placeholder+"/path"})

    def test_symlinked_code_cannot_enter_bundle(self):
        source = self.root/"source"
        shutil.copytree(ROOT/"router_core", source/"router_core", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT/"scripts", source/"scripts", ignore=shutil.ignore_patterns("__pycache__", "spikes"))
        shutil.copyfile(ROOT/"LICENSE", source/"LICENSE")
        (source/"router_core/private.env").write_text("must-not-be-copied")
        (source/"router_core/foreign.py").symlink_to(ROOT/"router_core/native.py")
        with self.assertRaises(PackageError):
            build_codex_package(self.output, self.bindings, source_root=source)
        self.assertFalse(self.output.exists())

    def test_native_source_spelling_is_not_canonicalized(self):
        alias = self.root/"reviewed-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        bindings = replace(self.bindings, project=str(alias))
        build_codex_package(self.output, bindings)
        command = json.loads((self.output/"plugins"/NAME/"hooks/hooks.json").read_text())["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        self.assertIn(str(alias), command)

    def test_content_addressed_versions_are_stable_and_change_with_bindings(self):
        first = build_codex_package(self.output, self.bindings)
        same = build_codex_package(self.root/"same", self.bindings)
        changed = build_codex_package(self.root/"changed", replace(self.bindings, global_config=str(self.root/"other.json")))
        self.assertRegex(first["version"], r"^0\.1\.0\+[a-f0-9]{12}$")
        self.assertEqual(first["version"], same["version"])
        self.assertNotEqual(first["version"], changed["version"])


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("codex_smoke", Path(__file__).resolve().parents[1]/"scripts/spikes/codex_route_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class CodexSpikeTests(unittest.TestCase):
    def test_fixture_is_valid_and_injected_provider_only(self):
        source = smoke.fixture_source(Path("/private/fixture"), Path("/private/fixture/state"))
        compile(source, "fixture", "exec")
        self.assertNotIn("JevClient", source)
        self.assertNotIn("TYPESAFE_API_KEY", source)
        self.assertIn("PreparationService", source)
        self.assertIn("NativeAdapter", source)
        self.assertIn("bypassPermissions", source)

    def test_live_fixture_uses_shipped_synthetic_task_and_unmodified_policy_threshold(self):
        source = smoke.fixture_source(Path("/fixture"), Path("/fixture/state"), live_jev=True,
            sdk_python="/trusted/pinned-python", catalog_json='{"schema_version":1,"entries":[]}')
        compile(source, "fixture", "exec")
        self.assertIn("JevClient", source)
        self.assertIn("load_private_key", source)
        self.assertNotIn("min_confidence_for_auto", source)
        self.assertNotIn("api_key=\"", source)
        self.assertNotIn("retry_count", source)
        corpus = json.loads((Path(__file__).resolve().parent/"fixtures/intelligent-router/representative-corpus.json").read_text())
        task = next(t for t in corpus["task_cases"] if t["id"] == "TASK-011")
        self.assertEqual(smoke.LIVE_TASK, task["description"])
        with self.assertRaises(ValueError):
            smoke.fixture_source(Path("/fixture"), Path("/state"), live_jev=True)

    def test_restores_existing_files_and_removes_created_helpers_on_error(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p/"hook.py").write_bytes(b"original")
            (p/"hook.py").chmod(0o640)
            with self.assertRaises(RuntimeError):
                with smoke.replaced_files(p, {"hook.py": "new", "helper.py": "temp"}):
                    raise RuntimeError()
            self.assertEqual((p/"hook.py").read_bytes(), b"original")
            self.assertEqual((p/"hook.py").stat().st_mode & 0o777, 0o640)
            self.assertFalse((p/"helper.py").exists())

    def test_symlinks_never_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p/"target").write_text("original")
            (p/"hook.py").symlink_to(p/"target")
            with self.assertRaises(ValueError):
                with smoke.replaced_files(p, {"hook.py": "new"}):
                    pass
            self.assertEqual((p/"target").read_text(), "original")

    def test_empty_evidence_cannot_pass(self):
        report = smoke.summarize([], [], [], Path("/imaginary"))
        self.assertNotEqual(report["status"], "passed")
        self.assertIn("expected_one_synthetic_classification", report["errors"])
        self.assertIn("native_child_model_missing_or_mismatch", report["errors"])

    def test_context_parser_is_scoped_to_synthetic_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/"transcript.jsonl"
            p.write_text('{"type":"turn_context","payload":{"cwd":"/other","model":"wrong"}}\n')
            self.assertEqual(smoke.synthetic_context(str(p), Path(directory)), {})

    def test_report_requires_preparation_reference_native_rewrite_and_contexts(self):
        original = {"message": "gAAAAopaque", "task_name": "router_" + "a"*48}
        updated = dict(original, model="gpt-6-luna", reasoning_effort="medium")
        rows = [
            {"event": {"hook_event_name": "SessionStart", "transcript_path": "parent.jsonl"}},
            {"event": {"hook_event_name": "PreToolUse", "tool_name": "collaborationspawn_agent", "tool_input": original},
             "output": {"hookSpecificOutput": {"updatedInput": updated, "permissionDecision": "allow"}}},
            {"event": {"hook_event_name": "PostToolUse", "tool_name": "collaborationspawn_agent", "tool_input": updated}},
            {"event": {"hook_event_name": "SubagentStart", "model": "gpt-6-luna"}},
            {"event": {"hook_event_name": "SubagentStop", "model": "gpt-6-luna", "agent_transcript_path": "child.jsonl", "last_assistant_message": "ROUTER_SMOKE_OK"}}]
        prep = [{"expected_synthetic": True, "opaque": False, "result": {"result": {"content": [{"text": json.dumps({"ok": True, "task_name": original["task_name"]})}]}}}]
        parent = {"model": "gpt-6.1-sol", "effort": "low", "approval_policy": "never", "sandbox_policy": {"type": "read-only"}}
        child = dict(parent, model="gpt-6-luna", effort="medium")
        def report():
            with patch.object(smoke, "synthetic_context", side_effect=[parent, child]):
                return smoke.summarize(rows, prep, [{"expected_synthetic": True}], Path("/fixture"))
        self.assertEqual(report()["status"], "passed")
        prep[0]["result"]["result"]["content"][0]["text"] = '{"ok":true,"task_name":"wrong"}'
        self.assertIn("prepared_reference_not_bound_to_spawn", report()["errors"])
        original["model"] = "explicit-pin"
        self.assertIn("original_spawn_pinned", report()["errors"])
        child["approval_policy"] = "on-request"
        self.assertIn("child_route_or_permission_context_mismatch", report()["errors"])

    def test_runner_preserves_reviewed_source_spelling_and_narrow_tool_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root/"actual"
            (workspace/".codex").mkdir(parents=True)
            (workspace/".codex/hooks.json").write_text('{}')
            (workspace/".codex/config.toml").write_text('# mcp_probe.py')
            alias = root/"reviewed-alias"
            alias.symlink_to(workspace, target_is_directory=True)
            home = root/"home"
            home.mkdir()
            process = SimpleNamespace(communicate=lambda **kw: ("", ""), returncode=0)
            with patch.object(Path, "home", return_value=home), patch.object(smoke.subprocess, "run", return_value=SimpleNamespace(stdout="codex-cli 0.163.0\n")), patch.object(smoke.subprocess, "Popen", return_value=process) as launch:
                smoke.run_synthetic(alias)
            args = launch.call_args.args[0]
            self.assertEqual(args[args.index("-C")+1], str(alias))
            self.assertNotIn("--dangerously-bypass-hook-trust", args)
            self.assertNotIn("--ignore-user-config", args)
            self.assertIn('mcp_servers.router_synthetic_p0.tools.prepare_task.approval_mode="approve"', args)
            self.assertFalse((workspace/"_core_fixture.py").exists())


if __name__ == "__main__":
    unittest.main()

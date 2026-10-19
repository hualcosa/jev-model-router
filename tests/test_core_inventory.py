import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from router_core.inventory import InventoryError, discover_codex_models, normalize_codex_models, read_codex_hooks, _MetadataSession
from router_core.native import bootstrap_profile


class InventoryTests(unittest.TestCase):
    def profile(self):
        return bootstrap_profile("codex", "cli", "0.163.0").spawn

    def model(self, name="gpt-6-luna", efforts=("low", "medium", "high")):
        return {"id": name, "model": name, "defaultReasoningEffort": "medium",
                "supportedReasoningEfforts": [{"reasoningEffort": e, "description": "Ignored prose API_KEY=private"} for e in efforts]}

    def normalize(self, entries):
        return normalize_codex_models(entries, self.profile(), verified_at="2026-10-19T00:00:00Z")

    def test_exact_generation_only_and_availability_provenance(self):
        result = self.normalize([self.model(), self.model("gpt-5.6-terra"), self.model("luna")])
        self.assertEqual([e["runtime_model_id"] for e in result["catalog"]["entries"]], ["gpt-6-luna"])
        self.assertIn("terra:6", result["missing_desired_targets"])
        self.assertEqual(result["catalog"]["entries"][0]["availability_source"], "user_assumption")
        self.assertEqual(result["inference_calls"], 0)
        self.assertNotIn("private", json.dumps(result))

    def test_all_desired_exact_models_are_supported_without_historical_substitution(self):
        result = self.normalize([self.model("gpt-6-luna"), self.model("gpt-6-terra"),
                                 self.model("gpt-6.1-sol"), self.model("gpt-6-astra")])
        self.assertEqual(result["missing_desired_targets"], [])
        self.assertEqual(len(result["catalog"]["entries"]), 4)

    def test_rejects_ambiguous_ids_duplicate_entries_bad_effort_and_default(self):
        bad = []
        m = self.model();m["id"] = "different";bad.append([m])
        bad.append([self.model(), self.model()])
        bad.append([self.model(efforts=("medium", "unknown"))])
        bad.append([self.model(efforts=("medium", "medium"))])
        bad.append([self.model(efforts=("low",))])
        for entries in bad:
            with self.subTest(entries=entries), self.assertRaisesRegex(InventoryError, "invalid_model_list"):
                self.normalize(entries)

    def run_worker(self, code, *, deadline=2, hooks=False):
        original = subprocess.Popen
        processes = []
        def launch(command, **kwargs):
            self.assertEqual(command, ["/fixture/codex", "app-server", "--listen", "stdio://"])
            process = original([sys.executable, "-u", "-c", code], **kwargs)
            processes.append(process)
            return process
        try:
            with patch("router_core.inventory.subprocess.run", return_value=SimpleNamespace(stdout=b"codex-cli 0.163.0\n")), patch("router_core.inventory.subprocess.Popen", side_effect=launch):
                if hooks:
                    return read_codex_hooks("/fixture/codex", self.profile(), "/fixture/project", deadline_seconds=deadline)
                return discover_codex_models("/fixture/codex", self.profile(), deadline_seconds=deadline)
        finally:
            self.assertTrue(processes)
            self.assertTrue(all(p.poll() is not None for p in processes))

    def test_public_protocol_pagination_no_thread_or_turn_or_private_methods(self):
        pages = [{"data": [self.model()], "nextCursor": "page-2"},
                 {"data": [self.model("gpt-6.1-sol")], "nextCursor": None}]
        code = '''import sys,json
pages=PAGES
for line in sys.stdin:
 r=json.loads(line)
 if r['method']=='initialized':continue
 if r['method']=='initialize':out={}
 elif r['method']=='model/list':
  out=pages.pop(0)
  if len(pages)==0 and r['params'].get('cursor')!='page-2':raise ValueError()
 else:raise ValueError('non-inventory method')
 print(json.dumps({'id':r['id'],'result':out}),flush=True)
'''.replace("PAGES", repr(pages))
        result = self.run_worker(code)
        self.assertEqual(len(result["catalog"]["entries"]), 2)

    def test_timeout_duplicate_json_and_server_errors_fail_safely(self):
        for code, deadline in (("import time;time.sleep(10)", .05),
                ('import sys;sys.stdin.readline();print(\'{"id":1,"id":1,"result":{}}\',flush=True);sys.stdin.read()', 1),
                ('import sys;sys.stdin.readline();print(\'{"id":1,"error":{"message":"private-secret"}}\',flush=True);sys.stdin.read()', 1)):
            with self.subTest(code=code), self.assertRaises(InventoryError) as error:
                self.run_worker(code, deadline=deadline)
            self.assertNotIn("private-secret", str(error.exception))

    def test_host_version_mismatch_never_starts_server(self):
        with patch("router_core.inventory.subprocess.run", return_value=SimpleNamespace(stdout=b"codex-cli 9.0.0\n")), patch("router_core.inventory.subprocess.Popen") as launch:
            with self.assertRaisesRegex(InventoryError, "host_version_mismatch"):
                discover_codex_models("/fixture/codex", self.profile())
            launch.assert_not_called()

    def test_hook_inventory_uses_only_public_metadata_and_rejects_incomplete_discovery(self):
        for warnings in ([], ["private-secret"]):
            code = '''import sys,json
for line in sys.stdin:
 r=json.loads(line)
 if r['method']=='initialized':continue
 if r['method']=='initialize':out={}
 elif r['method']=='hooks/list':
  if r['params']!={'cwds':['/fixture/project']}:raise ValueError()
  out={'data':[{'cwd':'/fixture/project','hooks':[],'warnings':WARNINGS,'errors':[]}]}
 else:raise ValueError('non-hook method')
 print(json.dumps({'id':r['id'],'result':out}),flush=True)
'''.replace("WARNINGS", repr(warnings))
            if warnings:
                with self.assertRaises(InventoryError) as error:
                    self.run_worker(code, hooks=True)
                self.assertNotIn("private-secret", str(error.exception))
            else:
                self.assertEqual(self.run_worker(code, hooks=True), [])

    def test_metadata_session_rejects_execution_and_private_methods_before_send(self):
        session = _MetadataSession("/fixture/codex", self.profile(), 1)
        try:
            for method in ("thread/start", "turn/start", "command/exec", "config/read", "fs/readFile"):
                with self.assertRaisesRegex(InventoryError, "metadata_method_forbidden"):
                    session.call(method, {})
        finally:
            session.__exit__(None, None, None)


if __name__ == "__main__":
    unittest.main()

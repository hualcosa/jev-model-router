import json
import os
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from router_core.claude_inventory import read_claude_hook_candidates
from router_core.inventory import InventoryError


def listing():
    return {"bareMode": {"exitHint": "fixture"}, "hooks": [{"event": "PreToolUse",
        "matcher": "Agent", "source": "userSettings", "type": "command",
        "commandText": "private-fixture", "disabled": True}],
        "policy": {"disabledByPolicy": False, "managedOnly": False, "pluginOnly": False,
                   "allDisabled": False, "policyHookCount": 0}}


class ClaudeInventoryTests(unittest.TestCase):
    def probe(self, data=None, *, code=None, deadline=1):
        original = subprocess.Popen
        processes = []
        if code is None:
            code = '''import sys,json
data=DATA
for index,line in enumerate(sys.stdin):
 request=json.loads(line)
 assert request['type']=='control_request'
 assert request['request']==({'subtype':'initialize','hooks':{}} if index==0 else {'subtype':'get_hooks_listing'})
 print(json.dumps({'type':'system','subtype':'ui_invalidate'}),flush=True)
 print(json.dumps({'type':'control_response','response':{'subtype':'success',
  'request_id':request['request_id'],'response':{} if index==0 else data}}),flush=True)
'''.replace("DATA", repr(data if data is not None else listing()))
        def launch(command, **kwargs):
            self.assertEqual(command, ["/fixture/claude", "-p", "--bare", "--input-format", "stream-json",
                "--output-format", "stream-json", "--verbose", "--strict-mcp-config",
                "--mcp-config", '{"mcpServers":{}}', "--tools", ""])
            self.assertEqual(kwargs.pop("cwd"), "/fixture/project")
            self.assertEqual(kwargs["env"]["ROUTER_DISABLE"], "1")
            self.assertNotIn("ANTHROPIC_API_KEY", kwargs["env"])
            process = original([sys.executable, "-u", "-c", code], **kwargs)
            processes.append(process)
            return process
        try:
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "never-forward"}), \
                    patch("router_core.claude_inventory.subprocess.run", return_value=SimpleNamespace(stdout=b"2.1.303 (Claude Code)\n")), \
                    patch("router_core.claude_inventory.subprocess.Popen", side_effect=launch):
                return read_claude_hook_candidates("/fixture/claude", "/fixture/project", deadline_seconds=deadline)
        finally:
            self.assertTrue(processes)
            self.assertTrue(all(p.poll() is not None for p in processes))

    def test_bare_metadata_only_sequence_and_cleanup(self):
        self.assertEqual(self.probe(), listing())

    def test_incomplete_policy_or_active_rows_rejected(self):
        cases = []
        for field, value in (("policyUnreadable", True), ("policyHookCount", 1),
                             ("policyHookCount", True), ("managedOnly", True)):
            item = listing(); item["policy"][field] = value; cases.append(item)
        item = listing(); item.pop("bareMode"); cases.append(item)
        item = listing(); item["errors"] = ["private-fixture"]; cases.append(item)
        item = listing(); item["hooks"][0].pop("disabled"); cases.append(item)
        item = listing(); item["hooks"][0]["matcher"] = None; cases.append(item)
        for item in cases:
            with self.subTest(item=item), self.assertRaises(InventoryError) as error:
                self.probe(item)
            self.assertNotIn("private-fixture", str(error.exception))

    def test_timeout_eof_duplicate_json_control_requests_and_flood(self):
        for code in ("import time;time.sleep(10)", "pass",
                     "print('{\"type\":\"control_response\",\"type\":\"control_response\"}',flush=True)",
                     "print('{\"type\":\"control_request\"}',flush=True)",
                     "print('{\"type\":\"user\"}',flush=True)",
                     "import sys;sys.stdout.write('x'*1100000);sys.stdout.flush()"):
            with self.subTest(code=code), self.assertRaises(InventoryError):
                self.probe(code=code, deadline=.15)

    def test_unknown_version_and_bad_input_never_launch(self):
        for kwargs in ({"version": "2.1.304"}, {"deadline_seconds": True}, {"deadline_seconds": float('nan')}):
            with patch("router_core.claude_inventory.subprocess.Popen") as launch:
                with self.assertRaises(InventoryError):
                    read_claude_hook_candidates("/fixture/claude", "/fixture/project", **kwargs)
                launch.assert_not_called()
        with patch("router_core.claude_inventory.subprocess.run", return_value=SimpleNamespace(stdout=b"2.1.304 (Claude Code)")), \
                patch("router_core.claude_inventory.subprocess.Popen") as launch:
            with self.assertRaisesRegex(InventoryError, "host_version_mismatch"):
                read_claude_hook_candidates("/fixture/claude", "/fixture/project")
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()

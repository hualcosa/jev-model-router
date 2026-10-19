import json
from pathlib import Path
import sys
import time
import unittest

from scripts.spikes import root_advisory_smoke as smoke


class RootSpikeTests(unittest.TestCase):
    def test_app_server_cleanup_bounds_inherited_pipe_after_parent_exit(self):
        # No Codex/provider call: leader exits, descendant holds stdout and
        # ignores TERM. Cleanup must kill the group and bound the final drain.
        child = ('import json,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                 'print(json.dumps({"method":"test/childReady"}),flush=True); time.sleep(30)')
        leader = ('import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",' + repr(child) + ']); time.sleep(.3)')
        start = time.monotonic()
        output, _stderr, result = smoke.run_app_server([sys.executable, "-c", leader], Path("/unused"))
        self.assertLess(time.monotonic()-start, 8)
        self.assertIn("test/childReady", output)
        self.assertIsNone(result["turn_status"])

    def rows(self):
        output = {"systemMessage": "synthetic warning", "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit", "additionalContext": "synthetic warning"}}
        return [{"event_name": "SessionStart", "model": "gpt-6-luna"},
            {"classification": True, "expected_synthetic": True},
            {"event_name": "UserPromptSubmit", "model": "gpt-6-luna", "turn_id_present": True,
             "expected_prompt": True, "output": output}]

    def test_fixture_uses_production_core_without_key_or_transcript_access(self):
        source = smoke.fixture_source(Path("/fixture"), Path("/state"), '{"entries":[]}')
        compile(source, "root-fixture", "exec")
        self.assertIn("NativeAdapter", source)
        self.assertIn('"mode":"warn"', source)
        self.assertNotIn("JevClient", source)
        self.assertNotIn("api_key", source)
        self.assertNotIn("transcript", source)

    def test_emission_alone_does_not_prove_warning_visibility(self):
        rows = self.rows()
        report = smoke.summarize(rows, "", 0)
        self.assertNotEqual(report["status"], "passed")
        self.assertIn("warning_not_observed_in_official_stream", report["errors"])
        stream = json.dumps({"method": "warning", "params": {"message": "synthetic warning"}})
        self.assertEqual(smoke.summarize(rows, stream, 0)["status"], "passed")

    def test_context_echo_is_not_user_warning_channel_evidence(self):
        rows = self.rows()
        stream = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "synthetic warning"}})
        self.assertNotEqual(smoke.summarize(rows, stream, 0)["status"], "passed")
        notification = {"method": "hook/completed", "params": {"run": {"eventName": "userPromptSubmit", "status": "completed",
            "entries": [{"kind": "warning", "text": "synthetic warning"}]}}}
        self.assertEqual(smoke.summarize(rows, json.dumps(notification), 0)["status"], "passed")

    def test_tui_requires_native_hook_presentation_marker_not_plain_echo(self):
        rows = self.rows()
        message = "Router advisory: gpt-6.1-sol"
        rows[-1]["output"]["systemMessage"] = message
        self.assertNotEqual(smoke.summarize(rows, message, 0, tui=True)["status"], "passed")
        self.assertEqual(smoke.summarize(rows, "↳ Hook · "+message, 0, tui=True)["status"], "passed")

    def test_missing_identity_wrong_model_extra_control_or_failed_process_cannot_pass(self):
        stream = json.dumps({"message": "synthetic warning"})
        for case in ("id", "model", "control", "count", "failed"):
            rows = self.rows()
            if case == "id":
                rows[-1]["turn_id_present"] = False
            elif case == "model":
                rows[0]["model"] = "wrong"
            elif case == "control":
                rows[-1]["output"]["decision"] = "block"
            elif case == "count":
                rows.append({"classification": True, "expected_synthetic": True})
            self.assertNotEqual(smoke.summarize(rows, stream, 1 if case == "failed" else 0)["status"], "passed")
        self.assertIsNone(smoke.summarize([], "", 0)["root_mutation_output"])


if __name__ == "__main__":
    unittest.main()

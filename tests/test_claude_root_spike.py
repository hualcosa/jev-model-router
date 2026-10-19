import copy
import hashlib
import subprocess
import sys
import unittest
from scripts.spikes.claude_root_smoke import summarize


def evidence():
    session="synthetic-session"
    stream=[{"type":"assistant","parent_tool_use_id":None,"message":{"model":"claude-haiku-5-5"}},
            {"type":"result","session_id":session,"is_error":False,"modelUsage":{"claude-haiku-5-5":{}}}]
    context={"session_hash":hashlib.sha256(session.encode()).hexdigest(),"output":None,
             "model_present":False,"prompt_id_present":False}
    rows=[dict(context,event="SessionStart"),dict(context,event="UserPromptSubmit",exact_synthetic_prompt=True)]
    return stream,rows


class ClaudeRootCapabilityEvidenceTests(unittest.TestCase):
    def test_missing_hook_fields_are_degraded_not_advisory_success(self):
        result=summarize(*evidence(),[],0)
        self.assertEqual(result["status"],"observed_degraded")
        self.assertEqual(result["classification_calls"],0)
        self.assertEqual(result["root_warning_count"],0)
        self.assertFalse(result["session_start_model_present"])
        self.assertFalse(result["user_prompt_id_present"])

    def test_model_change_mutation_fake_warning_and_mixed_session_rejected(self):
        for scenario in ("model","mutation","warning","session"):
            stream,rows=evidence()
            if scenario=="model":
                stream[0]["message"]["model"]="claude-opus-5-5"
            elif scenario=="mutation":
                rows[-1]["output"]={"continue":False}
            elif scenario=="warning":
                rows[-1]["output"]={"systemMessage":"unsupported root advice"}
            else:
                rows[-1]["session_hash"]="different"
            self.assertEqual(summarize(stream,rows,[],0)["status"],"unverified")

    def test_no_inference_without_switch(self):
        result=subprocess.run([sys.executable,"scripts/spikes/claude_root_smoke.py"],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,2)
        self.assertIn("--run-synthetic is required",result.stderr)


if __name__=="__main__":
    unittest.main()

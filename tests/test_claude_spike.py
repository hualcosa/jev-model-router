"""Conservative native smoke evidence checks; all inputs are synthetic."""
import copy
import subprocess
import sys
import unittest
from types import SimpleNamespace

from scripts.spikes.claude_route_smoke import summarize, summarize_telemetry, TASK, ROOT_MODEL, CHILD_MODEL


def evidence():
    original = {"prompt": TASK, "description": "synthetic", "subagent_type": "general-purpose"}
    events = [
        {"hook_event_name": "PreToolUse", "tool_name": "Agent", "effort": {"level": "high"},
         "tool_input": original},
        {"hook_event_name": "PostToolUse", "tool_name": "Agent", "effort": {"level": "high"},
         "tool_input": {**original, "model": "haiku", "effort": "medium"}},
        {"hook_event_name": "SubagentStop", "agent_id": "synthetic-child", "effort": {"level": "medium"}},
    ]
    events.insert(0, {"hook_event_name": "SessionStart", "model": ROOT_MODEL})
    for event in events:
        event["session_id"] = "synthetic-session"
    stream = [{"type":"assistant", "parent_tool_use_id":None, "session_id":"synthetic-session", "message":{"model": ROOT_MODEL}},
              {"type": "result", "session_id":"synthetic-session", "is_error": False,
               "modelUsage": {ROOT_MODEL: {"outputTokens":10}, CHILD_MODEL: {"outputTokens":5}}}]
    return stream, events


class ClaudeSpikeEvidenceTests(unittest.TestCase):
    def test_host_model_and_independent_effort_evidence(self):
        report = summarize(*evidence())
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["approval_decision_emitted"])
        self.assertEqual(report["root_efforts_reported"], ["high", "high"])
        self.assertEqual(report["child_efforts_reported"], ["medium"])

    def test_rewrite_alone_is_not_effective_execution(self):
        stream, events = evidence()
        stream[-1]["modelUsage"].pop(CHILD_MODEL)
        self.assertIn("effective_model_evidence_missing", summarize(stream, events)["errors"])

    def test_unknown_root_effort_is_not_inferred(self):
        stream, events = evidence()
        events[1]["effort"] = None
        self.assertIn("root_effort_unknown_or_changed", summarize(stream, events)["errors"])

    def test_changed_root_effort_fails(self):
        stream, events = evidence()
        events[2]["effort"] = {"level": "medium"}
        self.assertNotEqual(summarize(stream, events)["status"], "passed")

    def test_missing_child_effort_fails(self):
        stream, events = evidence()
        events[3].pop("effort")
        self.assertIn("child_effort_unknown_or_mismatch", summarize(stream, events)["errors"])

    def test_prompt_or_permissions_mutation_fails(self):
        for key, value in [("prompt", "changed"), ("permissions", "allow-all")]:
            stream, events = evidence()
            events[2]["tool_input"][key] = value
            self.assertIn("nonrouting_arguments_changed", summarize(stream, events)["errors"])

    def test_preexisting_pin_cannot_prove_unpinned_routing(self):
        stream, events = evidence()
        events[1]["tool_input"]["model"] = "sonnet"
        self.assertIn("original_spawn_was_pinned", summarize(stream, events)["errors"])

    def test_mixed_runs_rejected(self):
        stream, events = evidence()
        events.extend(copy.deepcopy(events))
        self.assertIn("expected_exactly_one_spawn", summarize(stream, events)["errors"])

    def test_root_identity_and_session_cannot_be_overridden_by_aggregate(self):
        for change in ("root", "session", "aggregate"):
            stream, events = evidence()
            if change == "root":
                events[0]["model"] = "claude-opus-5-5"
            elif change == "session":
                events[-1]["session_id"] = "different-session"
            else:
                stream[-1]["modelUsage"]["claude-opus-5-5"] = {}
            self.assertNotEqual(summarize(stream, events)["status"], "passed")

    def test_distinct_static_alias_probe_checks_requested_alias(self):
        stream, events = evidence()
        root, child = "claude-opus-5-5", ROOT_MODEL
        events[0]["model"] = root
        events[2]["tool_input"]["model"] = "sonnet"
        stream[-1]["modelUsage"] = {root: {"outputTokens":10}, child: {"outputTokens":5}}
        stream[0]["message"]["model"] = root
        self.assertEqual(summarize(stream, events, root_model=root, child_model=child, child_alias="sonnet")["status"], "passed")
        events[2]["tool_input"]["model"] = "haiku"
        self.assertNotEqual(summarize(stream, events, root_model=root, child_model=child, child_alias="sonnet")["status"], "passed")

    def test_public_root_message_required_and_zero_usage_rejected(self):
        for scenario in ("absent-optional-hook-model", "nested-only", "missing-marker", "zero-usage"):
            stream, events = evidence()
            events[0].pop("model")
            if scenario == "nested-only":
                stream[0]["parent_tool_use_id"] = "nested-child"
            elif scenario == "missing-marker":
                stream[0].pop("parent_tool_use_id")
            elif scenario == "zero-usage":
                stream[-1]["modelUsage"][CHILD_MODEL]["outputTokens"] = 0
            expected = scenario == "absent-optional-hook-model"
            self.assertEqual(summarize(stream,events)["status"] == "passed", expected)

    def test_telemetry_lifecycle_matches_only_its_own_agent_and_scope(self):
        base = dict(scope_hash="a"*64, runtime="claude", host_version="2.1.303", tool_hash=None, agent_hash=None)
        data = dict(actual_model=None, actual_effort=None, correlation="unverified", actual_execution="unverified")
        rows = [dict(base, source="assessment", data={"provider_calls":1}),
                dict(base, source="PostToolUse", tool_hash="b"*64,
                     data={**data, "argument_model":"haiku", "argument_effort":"medium"}),
                dict(base, source="SubagentStart", agent_hash="c"*64, data=data),
                dict(base, source="SubagentStop", agent_hash="c"*64,
                     data={**data,"actual_effort":"medium","actual_execution":"reported_by_host"})]
        def report(items):
            return summarize_telemetry([SimpleNamespace(to_dict=lambda row=row:row) for row in items])
        self.assertEqual(report(rows)["status"], "passed")
        for field, value in (("agent_hash", "d"*64), ("scope_hash", "d"*64), ("runtime", "codex"), ("host_version", "unknown")):
            changed = copy.deepcopy(rows)
            changed[-1][field] = value
            self.assertNotEqual(report(changed)["status"], "passed")

    def test_no_inference_without_explicit_switch(self):
        result = subprocess.run([sys.executable, "scripts/spikes/claude_route_smoke.py"],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--run-synthetic is required", result.stderr)


if __name__ == "__main__":
    unittest.main()

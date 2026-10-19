"""Adversarial permission-boundary fixtures, not a live sandbox proof."""
import copy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from router_core.config import merge_config_layers
from router_core.contracts import ProviderResult, ProviderStatus, TaskRequirements
from router_core.native import NativeAdapter, bootstrap_profile
from router_core.preparation import PreparationService
from router_core.privacy import SYNTHETIC_SMOKE
from router_core.state import PrivateStateStore


class SecurityBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = str(Path(self.tmp.name).resolve())
        self.store = PrivateStateStore(Path(self.project) / "state")
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def adapter(self, runtime):
        profile = bootstrap_profile(runtime, "cli", "2.1.303" if runtime == "claude" else "0.163.0")
        profile = replace(profile, conflicts_checked=True,
            safe_rewrite_permission_modes=frozenset({"default"} if runtime == "claude" else {"bypassPermissions"}))
        def classify(payload):
            self.calls.append(payload.provider_state())
            return ProviderResult(ProviderStatus.SUCCESS, TaskRequirements(0, 0, 0, .99, "T0", risk="low"))
        return NativeAdapter(profile, merge_config_layers({"mode": "auto_workers",
            "consent": {"synthetic_tasks": True}}, {}), self.store, classify, project_id=self.project)

    def event(self, runtime, **changes):
        event = dict(cwd=self.project, session_id="security-session", hook_event_name="PreToolUse",
            permission_mode="default" if runtime == "claude" else "bypassPermissions",
            tool_name="Agent" if runtime == "claude" else "collaborationspawn_agent",
            tool_use_id="security-call", tool_input={"prompt": SYNTHETIC_SMOKE} if runtime == "claude"
                else {"message": "gAAAA_opaque_fixture", "task_name": "ordinary"})
        event.update(changes)
        return event

    def assert_no_permission_output(self, output):
        if isinstance(output, dict):
            for key, value in output.items():
                self.assertNotIn(key, ("permissionDecision", "permissionDecisionReason",
                    "approval_policy", "sandbox_policy", "sandbox", "updatedInput"))
                self.assert_no_permission_output(value)
        elif isinstance(output, list):
            for value in output:
                self.assert_no_permission_output(value)

    def test_unrelated_tools_never_emit_permission_or_routing_overrides(self):
        for runtime in ("claude", "codex"):
            adapter = self.adapter(runtime)
            for tool in ("Bash", "Edit", "Read", "shell_command", "exec_command", "collaborationwait",
                         "mcp__untrusted__spawn_agent", "Bash; spawn_agent", "spawn_agent_suffix"):
                event = self.event(runtime, tool_name=tool, permissionDecision="allow",
                    sandbox_policy={"type": "danger-full-access"})
                before = copy.deepcopy(event)
                self.assertIsNone(adapter.handle(event))
                self.assertEqual(event, before)
        self.assertEqual(self.calls, [])

    def test_nonspawn_lifecycle_cannot_emit_permission_or_routing_overrides(self):
        for runtime in ("claude", "codex"):
            adapter = self.adapter(runtime)
            for i, name in enumerate(("SessionStart", "UserPromptSubmit", "PostToolUse", "SubagentStart",
                                      "SubagentStop", "TaskCreated", "TaskCompleted", "Stop", "PostCompact", "SessionEnd")):
                event = self.event(runtime, hook_event_name=name, event_id="event-" + str(i),
                    prompt=SYNTHETIC_SMOKE, permissionDecision="allow", model="unverified-root",
                    source="startup", prompt_id="prompt-" + str(i), turn_id="turn-" + str(i))
                before = copy.deepcopy(event)
                self.assert_no_permission_output(adapter.handle(event))
                self.assertEqual(event, before)

    def test_injected_spawn_permission_fields_are_rejected_before_classification(self):
        for runtime in ("claude", "codex"):
            adapter = self.adapter(runtime)
            for field in ("permissionDecision", "approval_policy", "sandbox_policy", "sandbox", "command", "env"):
                event = self.event(runtime)
                event["tool_input"][field] = "SYNTHETIC_PRIVATE_MARKER"
                before = copy.deepcopy(event)
                self.assertIsNone(adapter.handle(event))
                self.assertEqual(event, before)
        self.assertEqual(self.calls, [])
        for path in self.store.root.glob("*.json*"):
            self.assertNotIn("SYNTHETIC_PRIVATE_MARKER", path.read_text())

    def test_codex_unmeasured_permission_mode_never_consumes_prepared_capability(self):
        adapter = self.adapter("codex")
        adapter.handle(self.event("codex", hook_event_name="SessionStart"))
        prepared = PreparationService(adapter).prepare(session_id="security-session",
            task_text=SYNTHETIC_SMOKE, request_id="permission-modes")
        self.assertTrue(prepared["ok"])
        event = self.event("codex", tool_input={"message": "gAAAA_opaque_fixture", "task_name": prepared["task_name"]})
        for mode in (None, "", "default", "plan", "acceptEdits", "auto", "dontAsk", "future-mode"):
            before = copy.deepcopy(event)
            self.assertIsNone(adapter.handle({**event, "permission_mode": mode}))
            self.assertEqual(event, before)
        self.assertEqual(len(self.calls), 1)
        output = adapter.handle(event)["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "allow")
        self.assertEqual({k: v for k, v in output["updatedInput"].items()
                          if k not in ("model", "reasoning_effort")}, event["tool_input"])
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()

"""Structural child-spawn recognition: fail closed, with no classifier calls."""

import concurrent.futures
from dataclasses import replace
import unittest

from router_core.contracts import Runtime
from router_core.spawn import (
    AssessmentTracker,
    CapabilityProfile,
    SpawnAssessment,
    SpawnStatus,
    SpawnToolSchema,
    TrackerClaim,
    assess_child_spawn,
    _freeze_json,
)


def claude_profile():
    return CapabilityProfile(
        runtime=Runtime.CLAUDE,
        surface="cli",
        host_version="2.1.303",
        input_schema_version="claude-pretool-v1",
        tools={
            "Agent": SpawnToolSchema(
                argument_fields=frozenset({"description", "prompt", "model", "subagent_type", "run_in_background"}),
                task_field="prompt",
                field_types={
                    "description": frozenset({"string"}), "prompt": frozenset({"string"}),
                    "model": frozenset({"string", "null"}), "subagent_type": frozenset({"string"}),
                    "run_in_background": frozenset({"boolean"}),
                },
                pin_fields=frozenset({"model", "effort", "reasoning_effort"}),
                agent_type_field="subagent_type",
                generic_agent_types=frozenset({"general-purpose"}),
            ),
            "Task": SpawnToolSchema(
                argument_fields=frozenset({"description", "prompt", "model", "subagent_type", "run_in_background"}),
                task_field="prompt",
                field_types={
                    "description": frozenset({"string"}), "prompt": frozenset({"string"}),
                    "model": frozenset({"string", "null"}), "subagent_type": frozenset({"string"}),
                    "run_in_background": frozenset({"boolean"}),
                },
                pin_fields=frozenset({"model", "effort", "reasoning_effort"}),
                agent_type_field="subagent_type",
                generic_agent_types=frozenset({"general-purpose"}),
            ),
        },
    )


def codex_profile():
    schema = SpawnToolSchema(
        argument_fields=frozenset({"message", "task_name", "agent_type", "model", "reasoning_effort"}),
        task_field="message",
        field_types={
            "message": frozenset({"string"}), "task_name": frozenset({"string"}),
            "agent_type": frozenset({"string"}), "model": frozenset({"string", "null"}),
            "reasoning_effort": frozenset({"string", "null"}),
        },
        pin_fields=frozenset({"model", "effort", "reasoning_effort"}),
        agent_type_field="agent_type",
        generic_agent_types=frozenset({"default"}),
        plaintext_task=False,
    )
    # Names are exact identities from injected, version-bound evidence. This
    # fixture represents the observed flattened name plus two verified aliases.
    return CapabilityProfile(
        runtime=Runtime.CODEX,
        surface="cli-tui",
        host_version="0.163.0",
        input_schema_version="codex-pretool-v1",
        tools={"collaborationspawn_agent": schema, "spawn_agent": schema, "collaboration.spawn_agent": schema},
    )


class TestStructuralSpawn(unittest.TestCase):
    def setUp(self):
        self.profile = claude_profile()
        self.tracker = AssessmentTracker()

    def test_profile_cannot_hide_custom_type_or_claim_custom_is_generic(self):
        schema = self.profile.tools["Agent"]
        for changed in (replace(schema, agent_type_field=None),
                        replace(schema, generic_agent_types=frozenset({"security-reviewer"}))):
            with self.assertRaises(ValueError):
                replace(self.profile, tools={"Agent": changed})
        for size in (True, 0, 4097):
            with self.assertRaises(ValueError):
                AssessmentTracker(max_entries=size)

    def assess(self, **overrides):
        values = dict(
            profile=self.profile,
            event_name="PreToolUse",
            event_schema_version="claude-pretool-v1",
            tool_name="Agent",
            tool_input={"description": "Review tests", "prompt": "Inspect test coverage", "subagent_type": "general-purpose"},
            host_version="2.1.303",
            surface="cli",
            project_id="project-A",
            session_id="session-A",
            tool_use_id="tool-1",
            tracker=self.tracker,
        )
        values.update(overrides)
        return assess_child_spawn(**values)

    def test_verified_claude_agent_and_task_are_child_tasks(self):
        for tool_name in ("Agent", "Task"):
            result = self.assess(tool_name=tool_name, tool_use_id=tool_name)
            self.assertEqual(result.status, SpawnStatus.ELIGIBLE)
            self.assertEqual(result.envelope.task_text, "Inspect test coverage")
            self.assertEqual(result.envelope.task_binding.value, "native_plaintext")
            self.assertEqual(result.envelope.event.value, "subagent_spawn")

    def test_identity_is_deterministic_and_does_not_depend_on_task_text(self):
        one = self.assess(tool_use_id="one", tool_input={"prompt": "private A", "subagent_type": "general-purpose"})
        two = self.assess(tool_use_id="two", tool_input={"prompt": "private B", "subagent_type": "general-purpose"})
        self.assertNotEqual(one.task_id, two.task_id)
        again = assess_child_spawn(
            profile=self.profile, event_name="PreToolUse", event_schema_version="claude-pretool-v1",
            tool_name="Agent", tool_input={"prompt": "different task", "subagent_type": "general-purpose"},
            host_version="2.1.303", surface="cli", project_id="project-A", session_id="session-A",
            tool_use_id="one", tracker=AssessmentTracker(),
        )
        self.assertEqual(one.task_id, again.task_id)

    def test_nonnull_empty_pins_bypass_before_task_validation(self):
        for field in ("model", "effort", "reasoning_effort"):
            result = self.assess(tool_input={field: ""})
            self.assertEqual(result.status, SpawnStatus.PINNED)
            self.assertIsNone(result.envelope)

    def test_null_pin_does_not_bypass(self):
        result = self.assess(tool_input={"model": None, "prompt": "Task", "subagent_type": "general-purpose"})
        self.assertEqual(result.status, SpawnStatus.ELIGIBLE)

    def test_profiled_boolean_and_scalar_options_are_preserved(self):
        args = {"prompt": "Task", "subagent_type": "general-purpose", "run_in_background": False}
        result = self.assess(tool_input=args)
        self.assertEqual(result.status, SpawnStatus.ELIGIBLE)
        self.assertIs(result.copy_original_args()["run_in_background"], False)

    def test_unprofiled_boolean_option_is_rejected(self):
        result = self.assess(tool_input={"prompt": "Task", "subagent_type": "general-purpose", "unknown_bool": False})
        self.assertEqual(result.status, SpawnStatus.ABSTAIN)
        self.assertEqual(result.reason_code, "unknown_argument_schema")

    def test_custom_unknown_and_nontext_agent_types_skip(self):
        for index, (agent_type, expected) in enumerate((("custom-reviewer", SpawnStatus.CUSTOM_PROFILE), ("", SpawnStatus.CUSTOM_PROFILE), (4, SpawnStatus.ABSTAIN))):
            result = self.assess(tool_use_id=f"type-{index}", tool_input={"prompt": "Do work", "subagent_type": agent_type})
            self.assertEqual(result.status, expected)
            self.assertIsNone(result.envelope)

    def test_unrelated_tools_never_trigger_assessment(self):
        result = self.assess(tool_name="Bash")
        self.assertEqual(result.status, SpawnStatus.NOT_APPLICABLE)
        self.assertEqual(result.reason_code, "unrelated_tool")

    def test_missing_identity_unknown_schema_or_unsupported_version_abstain(self):
        for kwargs, reason in (
            ({"session_id": None}, "missing_project_or_session"),
            ({"project_id": ""}, "missing_project_or_session"),
            ({"tool_use_id": None}, "missing_tool_use_id"),
            ({"event_schema_version": "future-schema"}, "unknown_event_schema"),
            ({"host_version": "2.1.304"}, "unsupported_host_version"),
            ({"surface": "desktop"}, "unsupported_host_version"),
            ({"event_name": "PostToolUse"}, "not_pre_tool_use"),
        ):
            result = self.assess(**kwargs)
            self.assertEqual(result.status, SpawnStatus.ABSTAIN if reason != "not_pre_tool_use" else SpawnStatus.NOT_APPLICABLE)
            self.assertEqual(result.reason_code, reason)

    def test_missing_profile_and_unknown_tool_are_safe(self):
        self.assertEqual(self.assess(profile=None).status, SpawnStatus.ABSTAIN)
        self.assertEqual(self.assess(tool_name="MCP__spawn").status, SpawnStatus.NOT_APPLICABLE)
        self.assertEqual(self.assess(tool_name="Bash").status, SpawnStatus.NOT_APPLICABLE)

    def test_profile_rejects_non_native_creation_tools_and_unknown_types(self):
        schema = next(iter(self.profile.tools.values()))
        with self.assertRaises(ValueError):
            CapabilityProfile(Runtime.CLAUDE, "cli", "2.1.303", "schema", {"Bash": schema})
        with self.assertRaises(ValueError):
            SpawnToolSchema(
                argument_fields=frozenset({"prompt"}), task_field="prompt",
                field_types={"prompt": frozenset({"list"})},
            )

    def test_blank_and_malformed_context_or_task_safely_abstain(self):
        for index, kwargs in enumerate((
            {"project_id": " \t "}, {"session_id": "\n"}, {"tool_use_id": " "},
            {"session_id": "bad\ud800"},
        )):
            values = {"tool_use_id": f"ctx-{index}"}
            values.update(kwargs)
            self.assertEqual(self.assess(**values).status, SpawnStatus.ABSTAIN)
        for index, text in enumerate(("", "  \t ", "bad\ud800")):
            result = self.assess(tool_use_id=f"task-{index}", tool_input={"prompt": text, "subagent_type": "general-purpose"})
            self.assertEqual(result.status, SpawnStatus.ABSTAIN)

    def test_unknown_fields_nontext_and_multimodal_arguments_abstain(self):
        cases = (
            {"prompt": "task", "subagent_type": "general-purpose", "future_option": "x"},
            {"prompt": ["not", "text"], "subagent_type": "general-purpose"},
            {"prompt": {"type": "image", "data": "..."}, "subagent_type": "general-purpose"},
            {"prompt": "task", "subagent_type": "general-purpose", "tools": ["Bash"]},
        )
        for index, args in enumerate(cases):
            result = self.assess(tool_use_id=f"bad-{index}", tool_input=args)
            self.assertEqual(result.status, SpawnStatus.ABSTAIN)

    def test_oversize_input_abstains(self):
        result = self.assess(tool_input={"prompt": "x" * 100_001, "subagent_type": "general-purpose"})
        self.assertEqual(result.status, SpawnStatus.ABSTAIN)
        self.assertEqual(result.reason_code, "task_too_large")

    def test_codex_opaque_native_message_requires_local_preparation(self):
        result = assess_child_spawn(
            profile=codex_profile(), event_name="PreToolUse", event_schema_version="codex-pretool-v1",
            tool_name="collaborationspawn_agent",
            tool_input={"message": "gAAAAopaque-ciphertext", "task_name": "static-name-looking-like-task", "agent_type": "default"},
            host_version="0.163.0", surface="cli-tui", project_id="project-A", session_id="session-A",
            tool_use_id="codex-tool-1", tracker=AssessmentTracker(),
        )
        self.assertEqual(result.status, SpawnStatus.PREPARED_TASK_REQUIRED)
        self.assertIsNone(result.envelope)
        self.assertEqual(len(result.task_id), 70)
        self.assertEqual(result.reason_code, "plaintext_unavailable_requires_local_preparation")
        self.assertNotIn("ciphertext", repr(result))

    def test_codex_opaque_message_is_required_but_never_changes_identity(self):
        profile = codex_profile()

        def codex(message, tool_id):
            return assess_child_spawn(
                profile=profile, event_name="PreToolUse", event_schema_version="codex-pretool-v1",
                tool_name="collaborationspawn_agent", tool_input={"message": message, "agent_type": "default"},
                host_version="0.163.0", surface="cli-tui", project_id="p", session_id="s", tool_use_id=tool_id,
                tracker=AssessmentTracker(),
            )

        a = codex("gAAAAopaque-A", "same-tool")
        b = codex("gAAAAopaque-B", "same-tool")
        self.assertEqual(a.status, SpawnStatus.PREPARED_TASK_REQUIRED)
        self.assertEqual(a.task_id, b.task_id)
        self.assertEqual(codex("", "empty").status, SpawnStatus.ABSTAIN)
        self.assertEqual(codex(None, "nontext").status, SpawnStatus.ABSTAIN)
        self.assertEqual(codex("x" * 100_001, "oversize").reason_code, "task_too_large")

    def test_opaque_static_task_name_is_never_classified_and_pins_still_win(self):
        profile = codex_profile()
        result = assess_child_spawn(
            profile=profile, event_name="PreToolUse", event_schema_version="codex-pretool-v1",
            tool_name="spawn_agent", tool_input={"message": "gAAAAcipher", "task_name": "fix-the-security-bug", "agent_type": "default", "reasoning_effort": ""},
            host_version="0.163.0", surface="cli-tui", project_id="p", session_id="s", tool_use_id="id",
            tracker=AssessmentTracker(),
        )
        self.assertEqual(result.status, SpawnStatus.PINNED)

    def test_unknown_alias_is_not_recognized_unless_profile_includes_it(self):
        result = self.assess(tool_name="Agent.spawn_agent")
        self.assertEqual(result.status, SpawnStatus.NOT_APPLICABLE)

    def test_single_process_tracker_dedupes_by_runtime_project_session_tool_id(self):
        result = self.assess()
        duplicate = self.assess(tool_input={"prompt": "different", "subagent_type": "general-purpose"})
        self.assertEqual(result.status, SpawnStatus.ELIGIBLE)
        self.assertEqual(duplicate.status, SpawnStatus.DUPLICATE)
        # The same native tool ID in another project/session is independent.
        other = self.assess(project_id="project-B")
        self.assertEqual(other.status, SpawnStatus.ELIGIBLE)

    def test_tracker_capacity_refuses_new_keys_without_eviction(self):
        tracker = AssessmentTracker(max_entries=1)

        def call(tool_id):
            return assess_child_spawn(
                profile=self.profile, event_name="PreToolUse", event_schema_version="claude-pretool-v1",
                tool_name="Agent", tool_input={"prompt": "task", "subagent_type": "general-purpose"},
                host_version="2.1.303", surface="cli", project_id="p", session_id="s", tool_use_id=tool_id,
                tracker=tracker,
            )

        self.assertEqual(call("first").status, SpawnStatus.ELIGIBLE)
        self.assertEqual(call("first").status, SpawnStatus.DUPLICATE)
        full = call("second")
        self.assertEqual(full.status, SpawnStatus.ABSTAIN)
        self.assertEqual(full.reason_code, "tracker_full")
        self.assertEqual(tracker.claim(("claude", "p", "s", "first")), TrackerClaim.DUPLICATE)
        self.assertEqual(tracker.claim(("claude", "p", "s", "second")), TrackerClaim.FULL)

    def test_copy_budget_counts_empty_values_and_rejects_huge_or_invalid_values(self):
        self.assertIsNone(_freeze_json({str(i): "" for i in range(13_000)}))
        self.assertIsNone(_freeze_json({"big": 1 << 500}))
        self.assertIsNone(_freeze_json({"invalid": "\ud800"}))

    def test_tracker_is_at_most_once_under_concurrent_calls(self):
        tracker = AssessmentTracker()

        def call(_):
            return assess_child_spawn(
                profile=self.profile, event_name="PreToolUse", event_schema_version="claude-pretool-v1",
                tool_name="Agent", tool_input={"prompt": "task", "subagent_type": "general-purpose"},
                host_version="2.1.303", surface="cli", project_id="p", session_id="s", tool_use_id="concurrent",
                tracker=tracker,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(call, range(32)))
        self.assertEqual(sum(item.status is SpawnStatus.ELIGIBLE for item in results), 1)
        self.assertEqual(sum(item.status is SpawnStatus.DUPLICATE for item in results), 31)

    def test_original_arguments_are_safe_copy_and_not_repr_or_telemetry(self):
        private = "sensitive task text"
        result = self.assess(tool_input={"prompt": private, "subagent_type": "general-purpose"})
        self.assertIn(private, result.copy_original_args()["prompt"])
        self.assertNotIn(private, repr(result))
        self.assertNotIn(private, repr(result.safe_telemetry()))
        copied = result.copy_original_args()
        copied["prompt"] = "changed"
        self.assertEqual(result.copy_original_args()["prompt"], private)


if __name__ == "__main__":
    unittest.main()

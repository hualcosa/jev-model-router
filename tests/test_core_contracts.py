"""Tests for the versioned, runtime-neutral core contracts."""

import json
import math
import unittest

from router_core.contracts import (
    EventKind,
    ProviderResult,
    ProviderStatus,
    RouteDecision,
    RouteDisposition,
    Runtime,
    TaskBinding,
    TaskEnvelope,
    TaskRequirements,
    TaskTier,
)


class ContractTests(unittest.TestCase):
    def envelope(self, **changes):
        values = dict(runtime="codex", event="subagent_spawn", session_id="s1", task_id="t1",
                      task_text="private task details", has_custom_or_unknown_profile=False)
        values.update(changes)
        return TaskEnvelope(**values)

    def requirements(self, **changes):
        values = dict(complexity=0.25, reasoning=0.5, tool_complexity=0.2,
                      confidence=0.9, tier="T1", risk="low")
        values.update(changes)
        return TaskRequirements(**values)

    def test_all_contracts_round_trip_versioned_json(self):
        envelope = self.envelope(decision_reference="decision-2", task_binding=TaskBinding.UNKNOWN)
        req = self.requirements(ambiguity=0.1, provider_raw_tier="tier-1")
        provider = ProviderResult(ProviderStatus.SUCCESS, req, provider="jev")
        decision = RouteDecision(RouteDisposition.ROUTE_WORKER, "classified", "policy-v1", EventKind.SUBAGENT_SPAWN,
                                 selected_model="gpt-6-luna", selected_effort="medium", confidence=0.9,
                                 provenance="user_assumption", catalog_source="account_catalog")
        for value, cls in ((envelope, TaskEnvelope), (req, TaskRequirements),
                           (provider, ProviderResult), (decision, RouteDecision)):
            with self.subTest(contract=cls.__name__):
                encoded = value.to_json()
                self.assertEqual(json.loads(encoded)["schema_version"], 1)
                self.assertEqual(cls.from_json(encoded), value)

    def test_explicit_empty_model_and_effort_are_preserved_as_pins(self):
        env = self.envelope(explicit_model="", explicit_effort="")
        self.assertEqual(env.explicit_model, "")
        self.assertEqual(env.explicit_effort, "")
        parsed = TaskEnvelope.from_dict(env.to_dict())
        self.assertEqual(parsed.explicit_model, "")
        self.assertEqual(parsed.explicit_effort, "")

    def test_safe_telemetry_omits_task_plaintext(self):
        env = self.envelope(task_text="DO NOT LOG THIS SECRET TASK")
        telemetry = env.safe_telemetry()
        self.assertNotIn("task_text", telemetry)
        self.assertNotIn("DO NOT LOG THIS SECRET TASK", json.dumps(telemetry))
        self.assertEqual(env.to_dict()["task_text"], "DO NOT LOG THIS SECRET TASK")

    def test_telemetry_excludes_all_untrusted_text_and_bearer_references(self):
        env = self.envelope(session_id="sensitive-id", task_id="sensitive-task",
                            explicit_model="private-model-pin", explicit_effort="private-effort-pin",
                            explicit_agent_type="private-profile", decision_reference="bearer-token",
                            active_root_model="private-root", turn_id="private-turn")
        encoded = json.dumps(env.safe_telemetry())
        for marker in ("sensitive", "private", "bearer", "details"):
            self.assertNotIn(marker, encoded)
        self.assertTrue(env.safe_telemetry()["has_model_pin"])

    def test_json_duplicate_keys_rejected(self):
        data = self.envelope().to_json()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            TaskEnvelope.from_json(data[:-1] + ',"runtime":"claude"}')

    def test_missing_event_and_version_are_clear_validation_errors(self):
        decision = RouteDecision(RouteDisposition.SKIP, "pinned", "v1", EventKind.SUBAGENT_SPAWN)
        for key in ("event", "schema_version"):
            data = decision.to_dict()
            del data[key]
            with self.assertRaises(ValueError):
                RouteDecision.from_dict(data)

    def test_provider_failure_is_distinct_from_low_confidence_success(self):
        low = ProviderResult(ProviderStatus.SUCCESS, self.requirements(confidence=0.1), provider="jev")
        unavailable = ProviderResult(ProviderStatus.UNAVAILABLE, reason_code="missing_key")
        failure = ProviderResult(ProviderStatus.FAILURE, reason_code="invalid_schema")
        self.assertEqual(low.status, ProviderStatus.SUCCESS)
        self.assertEqual(low.requirements.confidence, 0.1)
        self.assertIsNone(unavailable.requirements)
        self.assertIsNone(failure.requirements)

    def test_root_decision_cannot_select_worker_route(self):
        with self.assertRaises(ValueError):
            RouteDecision(RouteDisposition.ROUTE_WORKER, "x", "v1", EventKind.ROOT_PROMPT, selected_model="model")
        with self.assertRaises(ValueError):
            RouteDecision(RouteDisposition.WARN_ROOT, "x", "v1", EventKind.ROOT_PROMPT,
                          selected_model="model", recommended_model="other")

    def test_warn_root_may_only_be_emitted_for_root_events(self):
        with self.assertRaises(ValueError):
            RouteDecision(RouteDisposition.WARN_ROOT, "x", "v1", EventKind.PREPARED_TASK,
                          recommended_model="model")

    def test_unknown_fields_and_schema_versions_are_rejected(self):
        data = self.envelope().to_dict()
        data["future"] = "unexpected"
        with self.assertRaisesRegex(ValueError, "unknown field"):
            TaskEnvelope.from_dict(data)
        data = self.envelope().to_dict()
        data["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "schema_version"):
            TaskEnvelope.from_dict(data)
        with self.assertRaisesRegex(ValueError, "field names"):
            TaskEnvelope.from_dict({1: "not a JSON object field"})

    def test_missing_required_fields_are_rejected(self):
        data = self.envelope().to_dict()
        del data["task_id"]
        with self.assertRaisesRegex(ValueError, "missing required"):
            TaskEnvelope.from_dict(data)

    def test_scores_reject_bool_nonfinite_and_out_of_range(self):
        for bad in (True, False, math.nan, math.inf, -math.inf, -0.01, 1.01, "0.5"):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                self.requirements(confidence=bad)

    def test_enum_values_and_required_ids_are_strict(self):
        with self.assertRaises(ValueError):
            self.envelope(runtime="claude-code")
        with self.assertRaises(ValueError):
            self.envelope(session_id="  ")
        with self.assertRaises(ValueError):
            self.envelope(has_custom_or_unknown_profile=1)

    def test_provider_result_shape_is_consistent(self):
        with self.assertRaises(ValueError):
            ProviderResult(ProviderStatus.SUCCESS)
        with self.assertRaises(ValueError):
            ProviderResult(ProviderStatus.FAILURE, self.requirements())

    def test_json_parser_rejects_non_json_numbers(self):
        with self.assertRaises(ValueError):
            TaskRequirements.from_json('{"schema_version":1,"complexity":NaN}')


if __name__ == "__main__":
    unittest.main()

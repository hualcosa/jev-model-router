import json
import unittest

from router_core.catalog import (
    CapabilityRecord,
    CatalogError,
    CatalogRegistry,
    ModelTarget,
)
from router_core.contracts import Runtime


REQUIRED_TARGETS = (
    ModelTarget("fable", "5.1"),
    ModelTarget("luna", "6"),
    ModelTarget("terra", "6"),
    ModelTarget("sol", "6.1"),
    ModelTarget("astra", "6"),
)


def entry(**changes):
    value = {
        "runtime": "codex",
        "surface": "cli",
        "host_version": "0.163.0",
        "family": "luna",
        "target_version": "6",
        "runtime_model_id": "gpt-6-luna",
        "tool_name": "spawn_agent",
        "model_field": "model",
        "effort_field": "reasoning_effort",
        "supported_efforts": ["low", "medium", "high"],
        "mapping_status": "verified",
        "mapping_evidence": "Native SubagentStart/Stop and host settings in synthetic CLI smoke.",
        "mapping_provenance": "P0 Codex CLI spike",
        "verified_at": "2026-10-19T14:19:10Z",
        "availability_source": "user_assumption",
    }
    value.update(changes)
    return value


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.registry = CatalogRegistry.from_json(json.dumps({"schema_version": 1, "entries": [entry()]}))
        self.target = ModelTarget("luna", "6")

    def query(self, **changes):
        args = {
            "runtime": Runtime.CODEX,
            "surface": "cli",
            "host_version": "0.163.0",
            "target": self.target,
            "effort": "medium",
            "tool_name": "spawn_agent",
            "model_field": "model",
        }
        args.update(changes)
        return self.registry.lookup(**args)

    def test_verified_mapping_is_eligible_and_preserves_distinct_target_and_runtime_id(self):
        result = self.query()
        self.assertTrue(result.eligible)
        self.assertEqual(result.record.target, self.target)
        self.assertEqual(result.record.runtime_model_id, "gpt-6-luna")

    def test_assumed_availability_does_not_turn_unverified_mapping_into_support(self):
        registry = CatalogRegistry((CapabilityRecord(**entry(mapping_status="unverified")),))
        result = registry.lookup(
            runtime="codex", surface="cli", host_version="0.163.0",
            target=self.target, effort="medium", tool_name="spawn_agent",
        )
        self.assertFalse(result.eligible)
        self.assertEqual(result.reason_code, "target_version_unverified")
        self.assertEqual(registry.records[0].availability_source, "user_assumption")

    def test_unknown_account_availability_is_not_routable(self):
        registry = CatalogRegistry((CapabilityRecord(**entry(availability_source="unknown")),))
        result = registry.lookup(
            runtime="codex", surface="cli", host_version="0.163.0",
            target=self.target, effort="medium", tool_name="spawn_agent",
        )
        self.assertEqual(result.reason_code, "account_availability_unknown")

    def test_version_mismatch_never_substitutes(self):
        registry = CatalogRegistry((CapabilityRecord(**entry(
            family="terra", target_version="5.6", runtime_model_id="terra", mapping_status="unverified",
        )),))
        result = registry.lookup(
            runtime="codex", surface="cli", host_version="0.163.0",
            target=ModelTarget("terra", "6"), effort="medium",
        )
        self.assertEqual(result.reason_code, "target_version_mismatch")

    def test_required_target_pins_are_exact_not_runtime_ids(self):
        self.assertEqual(
            [(target.family, target.target_version) for target in REQUIRED_TARGETS],
            [("fable", "5.1"), ("luna", "6"), ("terra", "6"), ("sol", "6.1"), ("astra", "6")],
        )

    def test_same_target_can_have_distinct_verified_native_tool_mappings(self):
        claude_agent = entry(
            runtime="claude", surface="cli", host_version="2.1.303",
            family="haiku", target_version="5.5", runtime_model_id="claude-haiku-5-5",
            tool_name="Agent", model_field="model", effort_field="effort", supported_efforts=["medium"],
            mapping_evidence="Native CLI execution reported this child model and effort.",
            mapping_provenance="P0 Claude CLI replay",
        )
        claude_task = dict(claude_agent, tool_name="Task")
        registry = CatalogRegistry((CapabilityRecord(**claude_agent), CapabilityRecord(**claude_task)))
        target = ModelTarget("haiku", "5.5")
        common = dict(runtime="claude", surface="cli", host_version="2.1.303", target=target, effort="medium")
        self.assertEqual(registry.lookup(**common).reason_code, "ambiguous_mapping")
        self.assertEqual(registry.lookup(**common, tool_name="Agent").record.tool_name, "Agent")
        self.assertEqual(registry.lookup(**common, tool_name="Task").record.tool_name, "Task")

    def test_scope_mismatches_and_unsupported_effort_are_excluded_with_reason_codes(self):
        self.assertEqual(self.query(runtime="claude").reason_code, "runtime_unverified")
        self.assertEqual(self.query(surface="desktop").reason_code, "surface_unverified")
        self.assertEqual(self.query(host_version="0.164.0").reason_code, "host_version_unverified")
        self.assertEqual(self.query(effort="xhigh").reason_code, "effort_unsupported")
        self.assertEqual(self.query(tool_name="other_tool").reason_code, "tool_unsupported")
        self.assertEqual(self.query(model_field="other_field").reason_code, "model_field_unsupported")

    def test_effort_rejected_when_runtime_exposes_no_effort_field(self):
        no_effort = CatalogRegistry((CapabilityRecord(**entry(effort_field=None, supported_efforts=[])),))
        result = no_effort.lookup(
            runtime="codex", surface="cli", host_version="0.163.0",
            target=self.target, effort="medium",
        )
        self.assertEqual(result.reason_code, "effort_unsupported")

    def test_snapshot_round_trip_is_stable(self):
        self.assertEqual(CatalogRegistry.from_json(self.registry.to_json()), self.registry)

    def test_snapshot_rejects_unknown_fields_duplicates_nonfinite_and_bool_version(self):
        raw = json.dumps({"schema_version": 1, "entries": [entry()]})
        bad = [
            raw.replace('"entries":', '"extra": 1, "entries":'),
            raw.replace('"family": "luna"', '"family": "luna", "family": "terra"'),
            '{"schema_version":NaN,"entries":[]}',
            json.dumps({"schema_version": True, "entries": []}),
        ]
        for snapshot in bad:
            with self.subTest(snapshot=snapshot[:30]):
                with self.assertRaises(CatalogError):
                    CatalogRegistry.from_json(snapshot)

    def test_snapshot_has_size_count_and_label_caps(self):
        with self.assertRaisesRegex(CatalogError, "size limit"):
            CatalogRegistry.from_json(" " * (1_048_576 + 1))
        many = {"schema_version": 1, "entries": [entry()] * 257}
        with self.assertRaises(CatalogError):
            CatalogRegistry.from_json(json.dumps(many))
        with self.assertRaises(CatalogError):
            CapabilityRecord(**entry(family="f" * 257))
        with self.assertRaises(CatalogError):
            CapabilityRecord(**entry(supported_efforts=[f"e{i}" for i in range(17)]))

    def test_duplicate_mapping_and_bool_efforts_fail_validation(self):
        with self.assertRaisesRegex(CatalogError, "duplicate catalog mapping"):
            CatalogRegistry((CapabilityRecord(**entry()), CapabilityRecord(**entry())))
        with self.assertRaises(CatalogError):
            CatalogRegistry((CapabilityRecord(**entry(supported_efforts=[True])),))

    def test_failure_messages_do_not_include_runtime_ids_or_raw_input(self):
        with self.assertRaises(CatalogError) as caught:
            CatalogRegistry.from_json('{"schema_version":1,"entries":[{"secret":"dont-leak"}]}')
        self.assertNotIn("dont-leak", str(caught.exception))

    def test_direct_lookup_rejects_malformed_target_and_effort_without_echoing_values(self):
        for kwargs in ({"target": "secret-target"}, {"effort": ["secret-effort"]}):
            args = {
                "runtime": "codex", "surface": "cli", "host_version": "0.163.0",
                "target": self.target, "effort": "medium",
            }
            args.update(kwargs)
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(CatalogError) as caught:
                    self.registry.lookup(**args)
                self.assertNotIn("secret", str(caught.exception))

    def test_known_native_fields_are_enforced_in_injected_snapshots(self):
        invalid = [
            entry(tool_name="Bash"),
            entry(runtime="claude", tool_name="Agent", effort_field="reasoning_effort"),
            entry(runtime="codex", effort_field="effort"),
            entry(model_field="model_name"),
        ]
        for record in invalid:
            with self.subTest(tool=record["tool_name"], effort_field=record["effort_field"]):
                with self.assertRaises(CatalogError):
                    CapabilityRecord(**record)

    def test_codex_observed_tool_spellings_are_allowed_only_by_exact_snapshot_match(self):
        for tool_name in ("spawn_agent", "collaboration.spawn_agent", "collaborationspawn_agent"):
            with self.subTest(tool_name=tool_name):
                mapped = CatalogRegistry((CapabilityRecord(**entry(tool_name=tool_name)),))
                result = mapped.lookup(
                    runtime="codex", surface="cli", host_version="0.163.0",
                    target=self.target, effort="medium", tool_name=tool_name,
                )
                self.assertTrue(result.eligible)
                self.assertEqual(result.record.tool_name, tool_name)
                self.assertEqual(
                    mapped.lookup(runtime="codex", surface="cli", host_version="0.163.0", target=self.target,
                                  effort="medium", tool_name="Bash").reason_code,
                    "tool_unsupported",
                )


if __name__ == "__main__":
    unittest.main()

from dataclasses import replace
import json
import unittest

from router_core.catalog import CapabilityRecord, CatalogRegistry, CatalogError
from router_core.config import merge_config_layers
from router_core.native import bootstrap_profile
from router_core.snapshots import VersionSnapshot
from tests.test_core_catalog import entry
from tests import test_native_adapter as native_helpers
from tests.test_root_advisory import _root_fixture


class RootIdentityContractTests(unittest.TestCase):
    def test_optional_ids_roundtrip_and_snapshot_binding(self):
        original = CapabilityRecord(**entry(mapping_provenance="synthetic_fixture"))
        old = CatalogRegistry((original,))
        self.assertNotIn("root_model_ids", old.to_json())
        source = ["observed-exact-id"]
        record = replace(original, root_model_ids=source)
        source.append("untrusted-mutation")
        registry = CatalogRegistry((record,))
        self.assertEqual(CatalogRegistry.from_json(registry.to_json()), registry)
        self.assertEqual(record.root_model_ids, ("observed-exact-id",))
        a = VersionSnapshot.capture("1", merge_config_layers({}, {}), old)
        b = VersionSnapshot.capture("1", merge_config_layers({}, {}), registry)
        self.assertNotEqual(a.snapshot_id, b.snapshot_id)
        self.assertNotEqual(a.catalog_id, b.catalog_id)
        self.assertEqual(VersionSnapshot.from_dict(b.to_dict()), b)

    def test_invalid_observed_ids_rejected(self):
        for invalid in ("not-a-list", None, {}, ["a"]*2, ["x"]*9, [""], [123], ["x\nsecret"], ["x"*257]):
            with self.subTest(invalid=invalid), self.assertRaises(CatalogError):
                replace(CapabilityRecord(**entry()), root_model_ids=invalid)
        obj = json.loads(CatalogRegistry((CapabilityRecord(**entry()),)).to_json())
        obj["entries"][0]["root_model_ids"] = "not-a-list"
        with self.assertRaises(CatalogError):
            CatalogRegistry.from_json(json.dumps(obj))

    def test_bootstrap_preserves_proven_worker_alias_and_exact_observation(self):
        profile = bootstrap_profile("claude", "cli", "2.1.303")
        r = profile.catalog.records[0]
        self.assertEqual(r.runtime_model_id, "haiku")
        self.assertEqual(r.root_model_ids, ("claude-haiku-5-5",))
        self.assertEqual(r.target_version, "5.5")
        self.assertEqual(bootstrap_profile("codex", "cli", "0.163.0").catalog.records[0].root_model_ids, ())


class RootIdentityNativeTests(unittest.TestCase):
    setUp = native_helpers.NativeAdapterTests.setUp
    tearDown = native_helpers.NativeAdapterTests.tearDown
    adapter = native_helpers.NativeAdapterTests.adapter
    classifier = native_helpers.NativeAdapterTests.classifier
    event = native_helpers.NativeAdapterTests.event

    def root(self, active="haiku", effort=None, tier="T1", *, observed="claude-haiku-5-5", aliases=None):
        adapter, event = _root_fixture(self, runtime="claude", active=active, effort=effort, tier=tier)
        adapter.profile = replace(adapter.profile, catalog=CatalogRegistry(tuple(
            replace(r, root_model_ids=(aliases or {}).get(r.family, (observed,) if r.family == active else ()))
            for r in adapter.profile.catalog.records)))
        event["session_id"] = "exact-root"
        adapter.handle(self.event("claude", hook_event_name="SessionStart", session_id="exact-root",
            model=observed, effort=effort, source="startup"))
        return adapter, event

    def test_canonical_observation_matches_only_explicit_alias_and_no_root_mutation(self):
        adapter, event = self.root()
        original = json.dumps(event, sort_keys=True)
        out = adapter.handle(event)
        self.assertIsNotNone(out)
        self.assertIn("fixture-sonnet", out["systemMessage"])
        self.assertIn("unknown effort", out["systemMessage"])
        self.assertEqual(json.dumps(event, sort_keys=True), original)
        self.assertNotIn("updatedInput", out["hookSpecificOutput"])
        self.assertEqual(len(self.calls), 1)
        for prompt_id, prompt in (("again", "continue"), ("later", "also add tests")):
            self.assertIsNone(adapter.handle({**event, "prompt_id": prompt_id, "prompt": prompt}))
        self.assertEqual(len(self.calls), 1)

    def test_same_capability_effort_advice_not_false_model_change(self):
        adapter, event = self.root(active="opus", effort="medium", tier="T2", observed="claude-opus-5-5")
        out = adapter.handle(event)
        self.assertIsNotNone(out)
        self.assertIn("higher effort on the same model", out["systemMessage"])
        self.assertIn("claude-opus-5-5 / high", out["systemMessage"])

    def test_unlisted_or_ambiguous_observation_and_unknown_effort_defer(self):
        for scenario in ("unlisted", "ambiguous", "unknown-effort"):
            with self.subTest(scenario=scenario):
                observed = "claude-opus-5-5"
                aliases = {"opus": (observed,)}
                if scenario == "unlisted":
                    aliases = {"opus": ("claude-opus-4-6",)}
                elif scenario == "ambiguous":
                    aliases["sonnet"] = (observed,)
                adapter, event = self.root(active="opus", effort=None, tier="T2", observed=observed, aliases=aliases)
                event["prompt_id"] = scenario
                self.assertIsNone(adapter.handle(event))

    def test_model_switch_uses_exact_observation_without_inheriting_old_effort(self):
        adapter, event = self.root(active="opus", effort="high", tier="T1", observed="claude-opus-5-5",
            aliases={"opus": ("claude-opus-5-5",), "haiku": ("claude-haiku-5-5",)})
        adapter.handle(self.event("claude", hook_event_name="PostModelSwitch", session_id="exact-root",
            to_model="claude-haiku-5-5", source="manual"))
        switches = [r.to_dict() for r in adapter.telemetry.read() if r.to_dict()["source"] == "PostModelSwitch"]
        self.assertEqual(len(switches), 1)
        self.assertEqual(switches[0]["data"]["actual_model"], "claude-haiku-5-5")
        self.assertEqual(switches[0]["data"]["actual_execution"], "reported_by_host")
        self.assertIsNone(switches[0]["data"]["actual_effort"])
        out = adapter.handle(event)
        self.assertIsNotNone(out)
        self.assertIn("unknown effort", out["systemMessage"])
        self.assertIsNone(adapter.handle({**event, "prompt_id": "other", "prompt": "continue"}))


if __name__ == "__main__":
    unittest.main()

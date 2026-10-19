from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from router_core.boundary import BoundaryScope
from router_core.catalog import CatalogRegistry
from router_core.config import DEFAULT_CONFIG, merge_config_layers
from router_core.contracts import RouteDecision
from router_core.policy import POLICY_VERSION, assess, decide
from router_core.snapshots import SnapshotError, VersionSnapshot
from router_core.state import PrivateStateStore, StateDisposition
from test_core_policy import fixture, fixture_catalog


class SnapshotTests(unittest.TestCase):
    def snapshot(self, *, config=DEFAULT_CONFIG, catalog=None, version=POLICY_VERSION):
        return VersionSnapshot.capture(version, config, catalog or fixture_catalog("codex"))

    def test_stable_ordering_and_canonical_roundtrip(self):
        cat = fixture_catalog("codex")
        one = self.snapshot(catalog=cat)
        two = self.snapshot(catalog=CatalogRegistry(tuple(reversed(cat.records))))
        self.assertEqual(one.snapshot_id, two.snapshot_id)
        self.assertEqual(one.catalog_id, two.catalog_id)
        self.assertEqual(VersionSnapshot.from_dict(one.to_dict()), one)
        raw = one.to_dict()
        raw["catalog"]["entries"].clear()
        self.assertTrue(json.loads(one.catalog_json)["entries"])

    def test_policy_config_version_and_catalog_changes_get_distinct_hashes(self):
        one = self.snapshot()
        for other in (self.snapshot(version="2.0.0"),
                      self.snapshot(config=merge_config_layers({"mode": "warn"}, {})),
                      self.snapshot(catalog=CatalogRegistry(fixture_catalog("codex").records[:1]))):
            self.assertNotEqual(one.snapshot_id, other.snapshot_id)
        self.assertEqual(one.catalog_id, self.snapshot(version="2.0.0").catalog_id)

    def test_freeform_evidence_never_persisted(self):
        cat = fixture_catalog("codex")
        cat = CatalogRegistry((replace(cat.records[0], mapping_evidence="Private API_KEY=super-secret /Users/private/path"),))
        raw = json.dumps(self.snapshot(catalog=cat).to_dict())
        self.assertNotIn("super-secret", raw)
        self.assertNotIn("/Users/private", raw)
        self.assertIn("mapping_evidence_sha256", raw)
        bad = CatalogRegistry((replace(cat.records[0], runtime_model_id="sk-proj-secret123456789"),))
        with self.assertRaises(SnapshotError):
            self.snapshot(catalog=bad)

    def test_rejects_tampered_unknown_duplicate_and_unsafe_metadata(self):
        one = self.snapshot()
        mutations = []
        raw = one.to_dict();raw["raw_prompt"] = "private";mutations.append(raw)
        raw = one.to_dict();raw["config"]["api_key"] = "private";mutations.append(raw)
        raw = one.to_dict();raw["catalog"]["entries"][0]["mapping_evidence"] = "private";mutations.append(raw)
        raw = one.to_dict();raw["catalog"]["entries"][0]["mapping_evidence_sha256"] = "invalid";mutations.append(raw)
        raw = one.to_dict();raw["catalog"]["entries"].append(raw["catalog"]["entries"][0]);mutations.append(raw)
        for raw in mutations:
            with self.subTest(raw=raw), self.assertRaisesRegex(SnapshotError, "invalid_version_snapshot"):
                VersionSnapshot.from_dict(raw)
        with self.assertRaises(SnapshotError):
            VersionSnapshot("1.0.0", '{"mode":"warn","mode":"disabled"}', one.catalog_json)

    def test_policy_decisions_include_ids_including_guard_and_provider_failure(self):
        env, provider, cat, cfg, scope = fixture({})
        expected = self.snapshot(config=cfg, catalog=cat)
        for decision in (decide(env, provider, cat, cfg, scope),
                         assess(env, lambda _: (_ for _ in ()).throw(ValueError()), cat, cfg, scope),
                         assess(replace(env, explicit_model="pinned"), lambda _: self.fail("provider"), cat, cfg, scope)):
            self.assertEqual(decision.version, POLICY_VERSION)
            self.assertEqual(decision.snapshot_version, expected.snapshot_id)
            self.assertEqual(decision.catalog_version, expected.catalog_id)
            self.assertEqual(RouteDecision.from_json(decision.to_json()), decision)

    def test_legacy_decisions_remain_exactly_decodable_after_policy_change(self):
        old = RouteDecision("defer", "old_reason", "0.9.0", "root_prompt").to_dict()
        self.assertNotIn("snapshot_version", old)
        new = self.snapshot(version="2.0.0")
        self.assertEqual(RouteDecision.from_dict(old).to_dict(), old)
        self.assertNotEqual(new.policy_version, old["version"])
        for bad in ({"snapshot_version": "a"*64},
                    {"snapshot_version": "bad", "catalog_version": "b"*64}):
            with self.assertRaises(ValueError):
                RouteDecision.from_dict({**old, **bad})

    def test_private_persistence_scope_ttl_and_historical_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            scope = BoundaryScope("codex", "project", "session")
            store = PrivateStateStore(Path(directory)/"state", clock=lambda: 1000)
            old = self.snapshot(version="0.9.0")
            new = self.snapshot(version="2.0.0")
            store.put_snapshot(scope, old);store.put_snapshot(scope, new)
            reopened = PrivateStateStore(Path(directory)/"state", clock=lambda: 1001)
            self.assertEqual(reopened.get_snapshot(scope, old.snapshot_id), old)
            self.assertEqual(reopened.get_snapshot(scope, new.snapshot_id), new)
            self.assertIsNone(reopened.get_snapshot(BoundaryScope("codex", "other", "session"), old.snapshot_id))
            self.assertEqual((Path(directory)/"state/state.json").stat().st_mode & 0o777, 0o600)
            expired = PrivateStateStore(Path(directory)/"state", clock=lambda: 1000+86401)
            self.assertIsNone(expired.get_snapshot(scope, old.snapshot_id))

    def test_legacy_private_decision_dedupe_survives_snapshot_additions(self):
        with tempfile.TemporaryDirectory() as directory:
            scope = BoundaryScope("codex", "project", "session")
            store = PrivateStateStore(Path(directory)/"state")
            old = RouteDecision("defer", "old_reason", "0.9.0", "root_prompt")
            store.run_once(scope, "tool", lambda: old)
            store.put_snapshot(scope, self.snapshot())
            replay = store.run_once(scope, "tool", lambda: self.fail("duplicate"))
            self.assertEqual(replay.disposition, StateDisposition.CACHED)
            self.assertEqual(replay.decision, old)


if __name__ == "__main__":
    unittest.main()

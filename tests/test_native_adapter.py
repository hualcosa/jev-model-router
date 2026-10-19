from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from router_core.catalog import CapabilityRecord, CatalogRegistry
from router_core.config import merge_config_layers
from router_core.contracts import ProviderResult, ProviderStatus, TaskRequirements
from router_core.native import NativeAdapter, bootstrap_profile
from router_core.preparation import PreparationService
from router_core.privacy import SYNTHETIC_SMOKE
from router_core.state import PrivateStateStore, StateScope
from router_core.snapshots import VersionSnapshot
from router_core.policy import POLICY_VERSION


class NativeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = os.path.realpath(self.tmp.name)
        self.store = PrivateStateStore(Path(self.project)/"state")
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def classifier(self, description):
        self.calls.append(description.provider_state())
        return ProviderResult(ProviderStatus.SUCCESS, TaskRequirements(0, 0, 0, 0.95, "T0", risk="low"))

    def adapter(self, runtime="claude", **changes):
        profile = bootstrap_profile(runtime, "cli", "2.1.303" if runtime == "claude" else "0.163.0")
        profile = replace(profile, conflicts_checked=True,
            safe_rewrite_permission_modes=frozenset({"default"} if runtime == "claude" else {"bypassPermissions"}))
        cfg = merge_config_layers({"mode": "auto_workers", "consent": {"synthetic_tasks": True}, **changes}, {})
        return NativeAdapter(profile, cfg, self.store, self.classifier, project_id=self.project)

    def event(self, runtime="claude", **changes):
        base = dict(cwd=self.project, session_id="session", hook_event_name="PreToolUse",
                    permission_mode="default" if runtime == "claude" else "bypassPermissions",
                    tool_name="Agent" if runtime == "claude" else "collaborationspawn_agent",
                    tool_input={"prompt": SYNTHETIC_SMOKE, "description": "Synthetic fixture"}
                        if runtime == "claude" else {"message": "gAAAA_opaque_fixture", "task_name": "ordinary_task"},
                    tool_use_id="call-1")
        base.update(changes)
        return base

    def test_claude_rewrites_only_supported_route_fields_and_keeps_native_permissions(self):
        adapter = self.adapter()
        event = self.event()
        original = json.loads(json.dumps(event))
        out = adapter.handle(event)["hookSpecificOutput"]
        self.assertEqual(out["updatedInput"], {**event["tool_input"], "model": "haiku", "effort": "medium"})
        self.assertNotIn("permissionDecision", out)
        self.assertEqual(event, original)
        self.assertEqual(len(self.calls), 1)
        again = adapter.handle(event)["hookSpecificOutput"]
        self.assertEqual(again, out)
        self.assertEqual(len(self.calls), 1)

    def test_pins_custom_profiles_unrelated_tools_missing_ids_and_shadow(self):
        adapter = self.adapter()
        for patch in ({"model": ""}, {"effort": "high"}, {"subagent_type": "security-reviewer"}):
            self.assertIsNone(adapter.handle(self.event(tool_input={"prompt": SYNTHETIC_SMOKE, **patch})))
        self.assertIsNone(adapter.handle(self.event(tool_name="Bash")))
        self.assertIsNone(adapter.handle(self.event(tool_use_id=None)))
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.adapter(mode="shadow").handle(self.event()))
        self.assertEqual(len(self.calls), 1)

    def test_no_real_task_transmission_under_synthetic_consent(self):
        out = self.adapter().handle(self.event(tool_input={"prompt": "Real confidential repository task"}))
        self.assertIsNone(out)
        self.assertEqual(self.calls, [])

    def test_unverified_conflicts_and_permission_modes_fail_before_provider(self):
        adapter = self.adapter()
        adapter.profile = replace(adapter.profile, conflicts_checked=False)
        self.assertIsNone(adapter.handle(self.event()))
        adapter = self.adapter("codex")
        self.assertIsNone(adapter.handle(self.event("codex", permission_mode="default")))
        self.assertEqual(self.calls, [])
        self.assertIsNone(bootstrap_profile("codex", "desktop", "0.163.0-alpha.10.2"))
        self.assertIsNone(bootstrap_profile("claude", "cli", "unknown"))

    def test_codex_registered_plaintext_preparation_and_single_use_reference(self):
        adapter = self.adapter("codex")
        service = PreparationService(adapter)
        args = dict(session_id="session", task_text=SYNTHETIC_SMOKE, request_id="mcp-call")
        self.assertFalse(service.prepare(**args)["ok"])
        start = adapter.handle(self.event("codex", hook_event_name="SessionStart", source="startup", model="gpt-6.1-sol"))
        self.assertIn("prepare_task", start["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.store.get_root(StateScope("codex", self.project, "session"))["model"], "gpt-6.1-sol")
        prepared = service.prepare(**args)
        self.assertTrue(prepared["ok"])
        self.assertEqual(service.prepare(**args), {"ok": False, "reason": "already_prepared"})
        self.assertNotIn("model", prepared)
        event = self.event("codex", tool_input={"message": "gAAAA_opaque_fixture", "task_name": prepared["task_name"]})
        out = adapter.handle(event)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "allow")
        self.assertEqual(out["updatedInput"], {**event["tool_input"], "model": "gpt-6-luna", "reasoning_effort": "medium"})
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(adapter.handle(event)["hookSpecificOutput"], out)
        self.assertIsNone(adapter.handle({**event, "tool_use_id": "another-call"}))
        self.assertEqual(len(self.calls), 1)

    def test_codex_opaque_unprepared_static_names_and_pins_never_classified(self):
        adapter = self.adapter("codex")
        self.assertIsNone(adapter.handle(self.event("codex")))
        event = self.event("codex", tool_input={"message": "opaque", "task_name": "router_"+"a"*48, "model": ""})
        self.assertIsNone(adapter.handle(event))
        self.assertEqual(self.calls, [])

    def test_prepared_codex_cannot_bypass_explicit_generic_type_restriction(self):
        adapter = self.adapter("codex", workers={"allow_verified_generic_type": False})
        adapter.handle(self.event("codex", hook_event_name="SessionStart"))
        prepared = PreparationService(adapter).prepare(session_id="session",
            task_text=SYNTHETIC_SMOKE, request_id="generic-control")
        self.assertTrue(prepared["ok"])
        event = self.event("codex", tool_input={"message": "gAAAA_opaque_fixture",
            "task_name": prepared["task_name"], "agent_type": "default"})
        before = json.loads(json.dumps(event))
        self.assertIsNone(adapter.handle(event))
        self.assertEqual(event, before)
        self.assertEqual(len(self.calls), 1)
        # Rejection must not consume the single-use reference. Implicit type
        # routing remains allowed by this explicit-generic-type-only control.
        event["tool_input"].pop("agent_type")
        event["tool_use_id"] = "implicit-call"
        self.assertIsNotNone(adapter.handle(event))
        self.assertEqual(len(self.calls), 1)

    def test_cached_prepared_codex_route_respects_later_generic_type_restriction(self):
        adapter = self.adapter("codex")
        adapter.handle(self.event("codex", hook_event_name="SessionStart"))
        prepared = PreparationService(adapter).prepare(session_id="session",
            task_text=SYNTHETIC_SMOKE, request_id="generic-revoke")
        event = self.event("codex", tool_input={"message": "gAAAA_opaque_fixture",
            "task_name": prepared["task_name"], "agent_type": "default"})
        self.assertIsNotNone(adapter.handle(event))
        adapter.config = merge_config_layers({"mode": "auto_workers",
            "consent": {"synthetic_tasks": True}, "workers": {"allow_verified_generic_type": False}}, {})
        self.assertIsNone(adapter.handle(event))
        self.assertEqual(len(self.calls), 1)

    def test_root_reset_then_observe_and_claude_switch_fields(self):
        adapter = self.adapter()
        scope = StateScope("claude", self.project, "session")
        adapter.handle(self.event(hook_event_name="SessionStart", model="claude-sonnet-5-5", source="startup"))
        self.assertEqual(self.store.get_root(scope)["model"], "claude-sonnet-5-5")
        adapter.handle(self.event(hook_event_name="PostModelSwitch", to_model="claude-opus-5-5", effort={"level": "high"}))
        self.assertEqual(self.store.get_root(scope), {"model": "claude-opus-5-5", "effort": "high"})
        adapter.handle(self.event(hook_event_name="SubagentStop", agent_id="child", model="haiku"))
        self.assertEqual(self.store.get_root(scope)["model"], "claude-opus-5-5")
        adapter.handle(self.event(hook_event_name="SessionStart", source="resume"))
        self.assertEqual(self.store.get_root(scope), {"model": None, "effort": None})

    def test_root_warning_visible_shape_nonblocking_and_once_per_task(self):
        adapter = self.adapter("codex")
        records = []
        for family, version in (("luna", "6"), ("sol", "6.1")):
            records.append(CapabilityRecord("codex", "cli", "0.163.0", family, version, "fixture-"+family,
                "collaborationspawn_agent", "model", "reasoning_effort", ("low", "medium", "high"),
                "verified", "Fake unit fixture only", "test_fixture", "2026-10-19T00:00:00Z"))
        adapter.profile = replace(adapter.profile, catalog=CatalogRegistry(tuple(records)))
        def difficult(description):
            self.calls.append(description.provider_state())
            return ProviderResult(ProviderStatus.SUCCESS, TaskRequirements(0.9, 0.9, 0.9, 0.95, "T2", risk="high"))
        adapter.classify = difficult
        # Use a trusted in-memory synthetic registry seam through policy's default
        # exact smoke fixture; structural marker isn't in that fixture, so give
        # a standalone meaningful initial synthetic task instead.
        event = self.event("codex", hook_event_name="UserPromptSubmit", prompt=SYNTHETIC_SMOKE,
                           model="fixture-luna", effort="low", turn_id="prompt-1")
        # The exact fixture starts with "List", which is a legitimate initial
        # mechanical task intent and must be recognized by the root gate.
        result = adapter.handle(event)
        self.assertIsNotNone(result)
        self.assertIn("fixture-sol", result["systemMessage"])
        self.assertNotIn("decision", result)
        self.assertNotIn("updatedInput", result["hookSpecificOutput"])
        self.assertIsNone(adapter.handle(event))
        self.assertEqual(len(self.calls), 1)

    def test_emergency_disable_hook_needs_no_runtime_key_config_or_stdin(self):
        cmd = [sys.executable, "scripts/router_hook.py", "--runtime", "codex", "--surface", "cli",
               "--runtime-binary", "/missing", "--project", self.project]
        proc = subprocess.run(cmd, env={**os.environ, "ROUTER_DISABLE": "1"}, input=b"private malformed",
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, b"", b""))

    def test_snapshot_is_durable_before_classification_and_stale_cache_never_rewrites(self):
        adapter = self.adapter()
        scope = StateScope("claude", self.project, "session")
        snapshot = VersionSnapshot.capture(POLICY_VERSION, adapter.config, adapter.profile.catalog)
        def classify(description):
            self.assertEqual(self.store.get_snapshot(scope, snapshot.snapshot_id), snapshot)
            return self.classifier(description)
        adapter.classify = classify
        self.assertIsNotNone(adapter.handle(self.event()))
        self.assertEqual(len(self.calls), 1)
        adapter.profile = replace(adapter.profile, catalog=CatalogRegistry(tuple(
            replace(r, mapping_provenance="new_inventory") for r in adapter.profile.catalog.records)))
        self.assertIsNone(adapter.handle(self.event()))
        self.assertEqual(len(self.calls), 1)

    def test_historical_unversioned_cache_decodes_but_has_no_current_route_authority(self):
        adapter = self.adapter()
        self.assertIsNotNone(adapter.handle(self.event()))
        path = Path(self.project)/"state/state.json"
        raw = json.loads(path.read_text())
        for record in raw["records"].values():
            if record["kind"] == "decision" and record["value"]["decision"]:
                record["value"]["decision"].pop("snapshot_version", None)
                record["value"]["decision"].pop("catalog_version", None)
        path.write_text(json.dumps(raw))
        self.assertIsNone(adapter.handle(self.event()))
        self.assertEqual(len(self.calls), 1)

    def test_long_lived_mcp_refresh_honors_revoked_consent_and_disabled_adapter(self):
        adapter = self.adapter("codex")
        adapter.handle(self.event("codex", hook_event_name="SessionStart", source="startup"))
        current = [adapter]
        service = PreparationService(None, refresh=lambda: current[0])
        first = service.prepare(session_id="session", task_text=SYNTHETIC_SMOKE, request_id="first")
        self.assertTrue(first["ok"])
        self.assertEqual(len(self.calls), 1)
        adapter.config = merge_config_layers({"mode": "auto_workers"}, {})
        second = service.prepare(session_id="session", task_text=SYNTHETIC_SMOKE, request_id="second")
        self.assertFalse(second["ok"])
        self.assertEqual(second["reason"], "no_consent_or_payload")
        self.assertEqual(len(self.calls), 1)
        current[0] = None
        self.assertEqual(service.prepare(session_id="session", task_text=SYNTHETIC_SMOKE, request_id="third"),
                         {"ok": False, "reason": "disabled_or_unsupported"})


if __name__ == "__main__":
    unittest.main()

import json
from pathlib import Path
import unittest

from router_core.catalog import CapabilityRecord, CatalogRegistry
from router_core.config import merge_config_layers
from router_core.contracts import (EventKind, ProviderResult, ProviderStatus, TaskBinding,
                                   TaskEnvelope, TaskRequirements)
from router_core.policy import PolicyScope, assess, decide
from router_core.privacy import SYNTHETIC_SMOKE


def fixture_catalog(runtime, **options):
    versions = ({"haiku": "5.5", "sonnet": "5.5", "opus": "5.5", "fable": "5.1"}
                if runtime == "claude" else {"luna": "6", "terra": "6", "sol": "6.1", "astra": "6"})
    records = []
    for family, version in versions.items():
        if options.get("wrong_version"):
            version = "historical-wrong-version"
        # These IDs and claims are deliberately fake test fixtures, NEVER an
        # installable registry or proof of account/runtime support.
        records.append(CapabilityRecord(runtime=runtime, surface="cli", host_version="fixture-v1",
            family=family, target_version=version, runtime_model_id=f"fixture-{family}",
            tool_name="Agent" if runtime == "claude" else "collaborationspawn_agent", model_field="model",
            effort_field=None if options.get("no_effort") else "effort" if runtime == "claude" else "reasoning_effort",
            supported_efforts=() if options.get("no_effort") else ("low", "medium", "high"),
            mapping_status="verified", mapping_evidence="Synthetic unit fixture only",
            mapping_provenance="test_fixture_not_runtime_evidence", verified_at="2026-10-19T00:00:00Z"))
    return CatalogRegistry(tuple(records))


def fixture(case):
    options = case.get("options", {})
    runtime = case.get("runtime", "codex")
    envelope = TaskEnvelope(runtime=runtime, event=options.get("event", "subagent_spawn"),
        session_id="fixture-session", task_id="fixture-task", task_text=SYNTHETIC_SMOKE,
        tool_call_id="fixture-tool", has_custom_or_unknown_profile=options.get("custom", False),
        task_binding=TaskBinding.NATIVE_PLAINTEXT, explicit_model=options.get("explicit_model"),
        explicit_effort=options.get("explicit_effort"),
        active_root_model=f"fixture-{options['active']}" if options.get("active") else None,
        active_root_effort=options.get("active_effort"))
    req = TaskRequirements(complexity=options.get("complexity", 0.1), reasoning=options.get("reasoning", 0.1),
        tool_complexity=0.1, confidence=options.get("confidence", 0.9), tier=case.get("tier", "T1"),
        risk=options.get("risk", "low"))
    provider = (ProviderResult(ProviderStatus.UNAVAILABLE, reason_code="missing_key")
                if options.get("provider") == "unavailable" else ProviderResult(ProviderStatus.SUCCESS, req))
    policy = {"frontier_auto_opt_in": options.get("frontier", False)}
    if "enabled" in options:
        policy["enabled_targets"] = options["enabled"]
    config = merge_config_layers({"mode": options.get("mode", "auto_workers"), "policy": policy,
                                  "consent": {"synthetic_tasks": True}}, {})
    catalog = fixture_catalog(runtime, **options)
    scope = PolicyScope("cli", "fixture-v1", "Agent" if runtime == "claude" else "collaborationspawn_agent")
    return envelope, provider, catalog, config, scope


class PolicyTests(unittest.TestCase):
    def test_pre_authored_golden_cases(self):
        corpus = json.loads((Path(__file__).parent / "fixtures/intelligent-router/policy-golden.json").read_text())
        self.assertGreaterEqual(len(corpus["cases"]), 28)
        for case in corpus["cases"]:
            with self.subTest(case=case["id"]):
                decision = decide(*fixture(case))
                expected = case["expected"]
                self.assertEqual(decision.disposition.value, expected["disposition"])
                model = decision.selected_model or decision.recommended_model
                self.assertEqual(model, f"fixture-{expected['family']}" if expected["family"] else None)
                self.assertEqual(decision.selected_effort or decision.recommended_effort, expected["effort"])
                if decision.event in (EventKind.ROOT_PROMPT, EventKind.PREFLIGHT):
                    self.assertIsNone(decision.selected_model)
                    self.assertIsNone(decision.selected_effort)

    def test_cheap_guards_and_consent_make_zero_provider_calls(self):
        cases = [{"options": {key: value}} for key, value in
                 (("explicit_model", ""), ("explicit_effort", ""), ("custom", True),
                  ("mode", "disabled"), ("mode", "warn"))]
        cases.append({"options": {"event": "root_prompt"}})
        for case in cases:
            env, provider, cat, cfg, scope = fixture(case)
            calls = []
            assess(env, lambda payload: calls.append(payload) or provider, cat, cfg, scope)
            self.assertEqual(calls, [])
        env, provider, cat, _, scope = fixture({})
        cfg = merge_config_layers({"mode": "auto_workers"}, {})
        calls = []
        decision = assess(env, lambda payload: calls.append(payload) or provider, cat, cfg, scope)
        self.assertEqual(calls, [])
        self.assertEqual(decision.reason_code, "no_consent_or_payload")

    def test_eligible_synthetic_assessment_calls_once_no_task_execution(self):
        env, provider, cat, cfg, scope = fixture({})
        calls = []
        decision = assess(env, lambda payload: calls.append(payload.provider_state()) or provider, cat, cfg, scope)
        self.assertEqual(calls, [{"task_summary": SYNTHETIC_SMOKE}])
        self.assertEqual(decision.selected_model, "fixture-sol")
        self.assertIsNone(env.explicit_model)

    def test_provider_errors_are_not_leaked_or_treated_as_simple(self):
        env, _, cat, cfg, scope = fixture({})
        def broken(_):
            raise RuntimeError("private task and key")
        decision = assess(env, broken, cat, cfg, scope)
        self.assertEqual(decision.disposition.value, "defer")
        self.assertNotIn("private", decision.to_json())

    def test_catalog_scope_unknown_binding_or_model_never_guessed(self):
        env, provider, cat, cfg, scope = fixture({})
        mismatch = decide(env, provider, cat, cfg, PolicyScope("desktop", "fixture-v1", scope.tool_name))
        self.assertEqual(mismatch.reason_code, "no_supported_route")
        raw = env.to_dict()
        raw["task_binding"] = "unknown"
        unknown = TaskEnvelope.from_dict(raw)
        calls = []
        decision = assess(unknown, lambda payload: calls.append(payload) or provider, cat, cfg, scope)
        self.assertEqual(calls, [])
        self.assertEqual(decision.reason_code, "task_binding_unknown")

    def test_project_restricted_generic_preflight_and_warning_flags_are_honored(self):
        for event, patch, agent_type in (
                ("subagent_spawn", {"workers": {"allow_verified_generic_type": False}}, "default"),
                ("preflight", {"boundary": {"explicit_preflight_enabled": False}}, None),
                ("root_prompt", {"root": {"warning_enabled": False}}, None)):
            env, provider, cat, _, scope = fixture({"options": {"event": event}})
            raw = env.to_dict()
            raw["explicit_agent_type"] = agent_type
            env = TaskEnvelope.from_dict(raw)
            cfg = merge_config_layers({"mode": "auto_workers", "consent": {"synthetic_tasks": True}, **patch}, {})
            calls = []
            decision = assess(env, lambda payload: calls.append(payload) or provider, cat, cfg, scope,
                              boundary_is_new=True)
            self.assertEqual(calls, [])
            self.assertEqual(decision.disposition.value, "skip")

    def test_explicit_preflight_works_without_inventing_an_active_root(self):
        env, provider, cat, cfg, scope = fixture({"options": {"event": "preflight"}})
        calls = []
        decision = assess(env, lambda payload: calls.append(payload) or provider, cat, cfg, scope)
        self.assertEqual(len(calls), 1)
        self.assertEqual(decision.reason_code, "preflight_recommendation")
        self.assertEqual(decision.recommended_model, "fixture-sol")
        self.assertIsNone(decision.selected_model)
        self.assertIsNone(env.active_root_model)

    def test_unknown_host_catalog_never_calls_provider(self):
        env, provider, cat, cfg, scope = fixture({})
        calls = []
        decision = assess(env, lambda payload: calls.append(payload) or provider, cat, cfg,
                          PolicyScope("desktop", "unknown", scope.tool_name))
        self.assertEqual(calls, [])
        self.assertEqual(decision.reason_code, "catalog_unavailable")

    def test_exhaustive_safety_floor_and_supported_effort_matrix(self):
        for runtime in ("claude", "codex"):
            for tier in ("T0", "T1", "T2", "T3"):
                for risk in ("low", "medium", "high"):
                    for confidence in (0, 0.74, 0.75, 1):
                        for mode in ("disabled", "shadow", "warn", "auto_workers"):
                            env, provider, cat, cfg, scope = fixture({"runtime": runtime, "tier": tier,
                                "options": {"risk": risk, "confidence": confidence, "mode": mode, "frontier": True}})
                            decision = decide(env, provider, cat, cfg, scope)
                            if mode != "auto_workers" or confidence < 0.75:
                                self.assertIsNone(decision.selected_model)
                            if decision.selected_model is not None:
                                record = next(r for r in cat.records if r.runtime_model_id == decision.selected_model)
                                self.assertIn(decision.selected_effort, record.supported_efforts)
                                if risk == "high":
                                    self.assertIn(record.family, ("opus", "fable", "sol", "astra"))
                                    self.assertEqual(decision.selected_effort, "high")


if __name__ == "__main__":
    unittest.main()

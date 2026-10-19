"""Stdlib-only tests for the strict, safety-bounded router config API."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from router_core.config import (
    CREDENTIAL_ENV,
    ConfigError,
    DEFAULT_CONFIG,
    MAX_DEADLINE_MS,
    MIN_DEADLINE_MS,
    load_config,
    merge_config_layers,
    parse_config,
)


def encode(value):
    return json.dumps(value, allow_nan=False)


class CoreConfigTests(unittest.TestCase):
    def assert_invalid(self, data, source="global"):
        with self.assertRaises(ConfigError):
            parse_config(encode(data), source=source)

    def test_missing_config_returns_safe_disabled_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = load_config(root / "missing-global.json", root / "missing-project.json")
        self.assertEqual(cfg, DEFAULT_CONFIG)
        self.assertEqual(cfg.mode, "disabled")
        self.assertFalse(cfg.consent.synthetic_tasks)
        self.assertFalse(cfg.consent.real_tasks)
        self.assertEqual(cfg.classification.retry_count, 0)
        self.assertEqual(cfg.classification.deadline_ms, MAX_DEADLINE_MS)
        self.assertEqual(cfg.classification.credential_env, "TYPESAFE_API_KEY")

    def test_project_layer_deep_overrides_without_erasing_siblings(self):
        global_layer = parse_config(encode({
            "mode": "auto_workers",
            "consent": {"synthetic_tasks": True},
            "classification": {"deadline_ms": 1200},
            "policy": {"enabled_targets": ["codex.sol", "codex.luna"], "min_confidence_for_auto": 0.75},
        }))
        project_layer = parse_config(encode({
            "mode": "shadow",
            "classification": {"deadline_ms": 900},
            "policy": {"enabled_targets": ["codex.sol"], "min_confidence_for_auto": 0.9},
        }), source="project")
        cfg = merge_config_layers(global_layer, project_layer)
        self.assertEqual(cfg.mode, "shadow")
        self.assertTrue(cfg.consent.synthetic_tasks)
        self.assertFalse(cfg.consent.real_tasks)
        self.assertEqual(cfg.classification.deadline_ms, 900)
        self.assertEqual(cfg.classification.retry_count, 0)
        self.assertEqual(cfg.policy.enabled_targets, frozenset({"codex.sol"}))
        self.assertEqual(cfg.policy.min_confidence_for_auto, 0.9)

    def test_project_can_revoke_but_never_grant_external_consent(self):
        global_layer = parse_config(encode({"consent": {"synthetic_tasks": True, "real_tasks": True}}))
        project_layer = parse_config(encode({"consent": {"real_tasks": False}}), source="project")
        cfg = merge_config_layers(global_layer, project_layer)
        self.assertTrue(cfg.consent.synthetic_tasks)
        self.assertFalse(cfg.consent.real_tasks)
        with self.assertRaisesRegex(ConfigError, "cannot grant external consent"):
            parse_config(encode({"consent": {"synthetic_tasks": True}}), source="project")
        with self.assertRaisesRegex(ConfigError, "cannot grant external consent"):
            merge_config_layers(global_layer, {"consent": {"real_tasks": True}})

    def test_config_is_immutable_and_includes_all_eight_candidate_families(self):
        cfg = merge_config_layers(parse_config(encode({})), {})
        self.assertEqual(cfg.policy.target_versions["claude"]["sonnet"], "5.5")
        self.assertEqual(cfg.policy.target_versions["claude"]["opus"], "5.5")
        self.assertEqual(cfg.policy.target_versions["claude"]["fable"], "5.1")
        self.assertEqual(cfg.policy.target_versions["codex"]["sol"], "6.1")
        self.assertNotIn("haiku", cfg.policy.target_versions["claude"])
        self.assertEqual(len(cfg.policy.enabled_targets), 8)
        self.assertIn("claude.haiku", cfg.policy.enabled_targets)
        with self.assertRaises(TypeError):
            cfg.policy.target_versions["codex"]["sol"] = "6"
        self.assert_invalid({"policy": {"target_versions": {"codex": {"sol": "6"}}}})

    def test_project_may_only_narrow_global_settings(self):
        cases = [
            ({"mode": "shadow"}, {"mode": "warn"}),
            ({"mode": "disabled"}, {"mode": "auto_workers"}),
            ({"policy": {"enabled_targets": ["codex.sol"]}}, {"policy": {"enabled_targets": ["codex.sol", "claude.haiku"]}}),
            ({"policy": {"frontier_auto_opt_in": False}}, {"policy": {"frontier_auto_opt_in": True}}),
            ({"policy": {"min_confidence_for_auto": 0.8}}, {"policy": {"min_confidence_for_auto": 0.7}}),
            ({"classification": {"deadline_ms": 1000}}, {"classification": {"deadline_ms": 1001}}),
            ({"root": {"warning_enabled": False}}, {"root": {"warning_enabled": True}}),
            ({"workers": {"allow_verified_generic_type": False}}, {"workers": {"allow_verified_generic_type": True}}),
            ({"boundary": {"explicit_preflight_enabled": False}}, {"boundary": {"explicit_preflight_enabled": True}}),
            ({"observability": {"log_decisions": False}}, {"observability": {"log_decisions": True}}),
        ]
        for global_cfg, project_cfg in cases:
            with self.subTest(global_cfg=global_cfg, project_cfg=project_cfg):
                global_layer = parse_config(encode(global_cfg))
                project_layer = parse_config(encode(project_cfg), source="project")
                with self.assertRaises(ConfigError):
                    merge_config_layers(global_layer, project_layer)

    def test_safety_invariants_cannot_be_disabled(self):
        cases = [
            {"root": {"preserve_model": False}},
            {"root": {"preserve_effort": False}},
            {"root": {"warning_once_per_task": False}},
            {"root": {"material_gain_only": False}},
            {"workers": {"route_unpinned_only": False}},
            {"workers": {"preserve_explicit_model": False}},
            {"workers": {"preserve_explicit_effort": False}},
            {"workers": {"preserve_custom_or_unknown_profile": False}},
            {"classification": {"send_full_transcript": True}},
            {"classification": {"minimize_task_payload": False}},
            {"boundary": {"classify_obvious_continuation": True}},
            {"observability": {"record_raw_prompt": True}},
            {"observability": {"private_state_permissions": False}},
            {"policy": {"require_verified_runtime_mapping": False}},
            {"policy": {"allow_implicit_version_substitution": True}},
        ]
        for config in cases:
            with self.subTest(config=config):
                self.assert_invalid(config)

    def test_strict_schema_rejects_unknown_values_types_and_bounds(self):
        cases = [
            {"schema_version": 2},
            {"unknown": 1},
            {"mode": "auto-root"},
            {"mode": "shadow", "classification": {"api_key": "do-not-echo"}},
            {"classification": {"credential_env": "PROJECT_SECRET"}},
            {"classification": {"deadline_ms": MIN_DEADLINE_MS - 1}},
            {"classification": {"deadline_ms": MAX_DEADLINE_MS + 1}},
            {"classification": {"deadline_ms": True}},
            {"classification": {"retry_count": 1}},
            {"classification": {"retry_count": 0.0}},
            {"consent": {"real_tasks": 1}},
            {"policy": {"enabled_targets": ["codex.sol", "codex.sol"]}},
            {"policy": {"enabled_targets": ["codex.nonexistent"]}},
            {"policy": {"min_confidence_for_auto": 1.1}},
            {"policy": {"min_confidence_for_auto": 10**1000}},
        ]
        for config in cases:
            with self.subTest(config=config):
                self.assert_invalid(config)
        self.assertEqual(CREDENTIAL_ENV, "TYPESAFE_API_KEY")

    def test_json_parser_rejects_duplicate_nonfinite_oversized_and_surrogate_input(self):
        raw_cases = [
            '{"mode":"shadow","mode":"warn"}',
            '{"policy":{"min_confidence_for_auto":NaN}}',
            " " * (64 * 1024 + 1),
            "\ud800",
        ]
        for raw in raw_cases:
            with self.subTest(raw_kind=len(raw)):
                with self.assertRaises(ConfigError) as caught:
                    parse_config(raw)
                self.assertIsNone(caught.exception.__cause__)

    def test_credential_values_and_invalid_file_contents_are_not_in_errors(self):
        with self.assertRaises(ConfigError) as caught:
            parse_config('{"classification":{"api_key":"super-secret-value"}}')
        self.assertNotIn("super-secret-value", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.json"
            bad.write_text('{"mode":"warn","classification":{"api_key":"secret"}}', encoding="utf-8")
            with self.assertRaises(ConfigError) as caught:
                load_config(bad)
            self.assertNotIn("secret", str(caught.exception))

    def test_unsafe_global_symlink_or_special_file_cannot_grant_consent(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            global_file = p / "global.json"
            global_file.write_text('{"consent":{"real_tasks":true}}')
            global_file.chmod(0o666)
            with self.assertRaises(ConfigError):
                load_config(global_file)
            global_file.chmod(0o600)
            self.assertTrue(load_config(global_file).consent.real_tasks)
            link = p / "link"
            link.symlink_to(global_file)
            with self.assertRaises(ConfigError):
                load_config(link)
            fifo = p / "fifo"
            os.mkfifo(fifo)
            with self.assertRaises(ConfigError):
                load_config(project_path=fifo)

    def test_invalid_direct_layers_and_deep_numeric_json_fail_safely(self):
        for layer in (None, [], "private config"):
            with self.assertRaises(ConfigError):
                merge_config_layers(layer, {})
        with self.assertRaises(ConfigError):
            parse_config('{"mode":' + '1'*10000 + '}')


if __name__ == "__main__":
    unittest.main()

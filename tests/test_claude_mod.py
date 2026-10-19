from dataclasses import replace
import tempfile
from pathlib import Path
import hashlib
import json
import unittest
from unittest.mock import patch

from router_core.claude_mod import proposal, verify_host
from router_core.config import merge_config_layers
from router_core.contracts import ProviderResult, ProviderStatus, TaskRequirements
from router_core.privacy import SYNTHETIC_SMOKE
from router_core.state import PrivateStateStore


class ClaudeModTests(unittest.TestCase):
    def test_companion_manifest_and_actual_entrypoint_are_attested(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root/"binary"
            binary.write_bytes(b"fixture native host")
            paths = [root/".claude-plugin/plugin.json", root/"hooks/claude-band.json",
                     root/"hooks/claude-codex-hooks.json", root/"hooks/band/register.tsx"]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture")
            files = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
            digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            with patch("router_core.claude_mod.NATIVE_SHA256", hashlib.sha256(binary.read_bytes()).hexdigest()), patch("router_core.claude_mod.COMPANION_SHA256", digest):
                self.assertTrue(verify_host(str(binary), str(root)))
                for path in paths[:3]:
                    path.write_text("changed module loading")
                    self.assertFalse(verify_host(str(binary), str(root)))
                    path.write_text("fixture")

    def test_proposal_keeps_only_model_effort_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            project = str(Path(directory).resolve())
            store = PrivateStateStore(Path(project)/"state")
            config = merge_config_layers({"mode": "auto_workers", "consent": {"synthetic_tasks": True}}, {})
            calls = []
            def classify(description):
                calls.append(description)
                return ProviderResult(ProviderStatus.SUCCESS, TaskRequirements(0, 0, 0, .99, "T0", risk="low"))
            event = dict(cwd=project, session_id="synthetic-mod-test", hook_event_name="PreToolUse",
                         tool_name="Agent", tool_use_id="call", tool_input={"prompt": SYNTHETIC_SMOKE})
            args = dict(project=project, version="2.1.303")
            self.assertEqual(proposal(event, config, store, classify, **args), {"model": "haiku", "effort": "medium"})
            self.assertEqual(proposal(event, config, store, classify, **args), {"model": "haiku", "effort": "medium"})
            self.assertEqual(len(calls), 1)
            for field, value in (("model", "sonnet"), ("effort", "high"), ("subagent_type", "custom")):
                pinned = {**event, "tool_input": {**event["tool_input"], field: value}}
                self.assertIsNone(proposal(pinned, config, store, classify, **args))
            self.assertEqual(len(calls), 1)
            self.assertIsNone(proposal(event, replace(config, mode="warn"), store, classify, **args))
            self.assertIsNone(proposal(event, config, store, classify, project=project, version="future"))

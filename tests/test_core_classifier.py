import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from router_core.classifier import JevClient
from router_core.contracts import ProviderStatus
from router_core.normalizer import normalize_response
from router_core.privacy import Consent, SYNTHETIC_SMOKE, build_task_description


def response():
    return {"schema_version": 1, "tier": {"choice": "T1", "confidence": 0.9},
            "risk": {"choice": "low", "confidence": 0.8},
            **{name: {"score": 0.44, "confidence": 0.85}
               for name in ("complexity", "reasoning", "tool_complexity")}}


class NormalizerTests(unittest.TestCase):
    def test_fractional_rubric_normalizes_without_inventing_confidence(self):
        req = normalize_response(response())
        self.assertEqual(req.reasoning, 0.22)
        self.assertEqual(req.confidence, 0.8)
        self.assertEqual(req.tier.value, "T1")

    def test_invalid_or_incomplete_answers_never_become_simple(self):
        for field in response():
            raw = response()
            del raw[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                normalize_response(raw)
        for value in (True, float("nan"), float("inf"), -0.01, 2.01, "0.4"):
            raw = response()
            raw["complexity"]["score"] = value
            with self.assertRaises(ValueError):
                normalize_response(raw)

    def test_reject_unknown_fields_versions_choices_confidences(self):
        for location, key, value in [(None, "extra", "bad"), (None, "schema_version", True),
                                     ("tier", "choice", "private-invalid"),
                                     ("risk", "choice", "critical"), ("risk", "confidence", 1.1),
                                     ("reasoning", "confidence", None), ("tier", "probabilities", {})]:
            raw = response()
            (raw if location is None else raw[location])[key] = value
            with self.assertRaises(ValueError) as error:
                normalize_response(raw)
            self.assertNotIn("private-invalid", str(error.exception))


class ClassifierTests(unittest.TestCase):
    def description(self):
        return build_task_description(SYNTHETIC_SMOKE, consent=Consent.SYNTHETIC)

    def client(self, source, **kwargs):
        return JevClient(api_key="fake-key-no-network", worker_command=[sys.executable, "-c", source], **kwargs)

    def test_valid_worker_response_and_minimal_payload(self):
        program = "import sys,json; p=json.load(sys.stdin); assert set(p)=={'api_key','task_summary','timeout_seconds'}; assert p['api_key']=='fake-key-no-network'; print(" + repr(json.dumps(response())) + ")"
        result = self.client(program).classify(self.description())
        self.assertEqual(result.status, ProviderStatus.SUCCESS)
        self.assertEqual(result.requirements.confidence, 0.8)

    def test_missing_key_and_raw_input_cannot_launch_process(self):
        client = JevClient(worker_command=["/not/a/program"])
        self.assertEqual(client.classify(self.description()).reason_code, "missing_key")
        self.assertEqual(client.classify("raw task").reason_code, "unprepared_task")

    def test_hard_deadline_kills_worker(self):
        start = time.monotonic()
        result = self.client("import time; time.sleep(10)", deadline_ms=100).classify(self.description())
        self.assertEqual(result.reason_code, "timeout")
        self.assertLess(time.monotonic() - start, 1.0)

    def test_sdk_unavailable_distinct_from_failed_and_low_confidence(self):
        result = self.client('print(\'{"error":"sdk_unavailable"}\')').classify(self.description())
        self.assertEqual(result.status, ProviderStatus.UNAVAILABLE)
        raw = response()
        raw["tier"]["confidence"] = 0.1
        result = self.client("print(" + repr(json.dumps(raw)) + ")").classify(self.description())
        self.assertEqual(result.status, ProviderStatus.SUCCESS)
        self.assertEqual(result.requirements.confidence, 0.1)

    def test_errors_never_include_output_or_key(self):
        for source in ('print("private-task fake-key-no-network")',
                       'import sys; print("private-task", file=sys.stderr); sys.exit(1)',
                       'print(\'{"error":"private-task"}\')',
                       'print(\'{"error":"sdk_unavailable","error":"sdk_unavailable"}\')',
                       'print("x"*20000)'):
            result = self.client(source).classify(self.description())
            self.assertEqual(result.status, ProviderStatus.FAILURE)
            self.assertNotIn("private-task", result.to_json())
            self.assertNotIn("fake-key", result.to_json())

    def test_invalid_options_are_sanitized(self):
        for deadline in (True, 0, 49, 2501, float("nan")):
            with self.assertRaises(ValueError):
                JevClient(deadline_ms=deadline)
        for key in ("private key", "\ud800", "nonascii-á", "\x00private"):
            with self.assertRaises(ValueError) as error:
                JevClient(api_key=key)
            self.assertNotIn("private key", str(error.exception))


class SDKWorkerTests(unittest.TestCase):
    def test_default_worker_isolates_sdk_imports_from_siblings_cwd_and_pythonpath(self):
        try:
            import typesafe_sdk  # noqa: F401
        except ImportError:
            self.skipTest("optional SDK absent; run in pinned private SDK venv")
        client = JevClient()
        self.assertEqual(client._command[:2], (sys.executable, "-I"))
        with tempfile.TemporaryDirectory() as directory:
            # The real worker already has router_core/packaging.py beside it.
            # Host project files/environment must not become SDK dependencies.
            for module in ("packaging", "typesafe_sdk"):
                # ImportError maps to sdk_unavailable, distinguishable from the
                # provider_failure expected only AFTER imports for empty input.
                Path(directory, module+".py").write_text("raise ImportError('untrusted import')")
            result = subprocess.run(client._command, input=b"{}", stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=directory, timeout=3,
                env={**os.environ, "PYTHONPATH": directory+os.pathsep+str(Path(client._command[-1]).parent)})
        self.assertEqual(result.returncode, 0)
        # Empty protocol input fails only AFTER SDK imports and BEFORE any key
        # access/client/network call. A shadowed SDK import was sdk_unavailable.
        self.assertEqual(json.loads(result.stdout), {"error": "provider_failure"})
        self.assertEqual(result.stderr, b"")

    def test_official_sdk_serialization_and_worker_answer_extraction(self):
        try:
            from typesafe_sdk import TypeSafeClient
            import httpx2
        except ImportError:
            self.skipTest("optional SDK absent; run in pinned private SDK venv")
        from router_core._jev_worker import request
        calls = []

        def mock(req):
            body = json.loads(req.content)
            calls.append(body)
            self.assertEqual(body["state"], {"task_summary": SYNTHETIC_SMOKE})
            self.assertEqual(set(body["questions"]), {"tier", "risk", "complexity", "reasoning", "tool_complexity"})
            answers = {
                "tier": {"type": "choice", "choice": "T0", "confidence": 0.9,
                         "probabilities": {"T0": 0.9, "T1": 0.1, "T2": 0.0, "T3": 0.0, "abstain": 0.0}},
                "risk": {"type": "choice", "choice": "low", "confidence": 0.8,
                         "probabilities": {"low": 0.8, "medium": 0.2, "high": 0.0}},
            }
            for name in ("complexity", "reasoning", "tool_complexity"):
                answers[name] = {"type": "score", "score": 0.25, "confidence": 0.75,
                                 "legend": {"0": "Low", "1": "Medium", "2": "High"},
                                 "probabilities": {"0": 0.75, "1": 0.25, "2": 0.0}}
            return httpx2.Response(200, json={"answers": answers, "model": "jev-test",
                                            "usage": {"input_tokens": 1, "output_tokens": 1}})

        def client(**kwargs):
            return TypeSafeClient(**kwargs, transport=httpx2.MockTransport(mock))

        with patch("typesafe_sdk.TypeSafeClient", client):
            raw = request({"api_key": "synthetic-test-key", "timeout_seconds": 2,
                           "task_summary": SYNTHETIC_SMOKE})
        req = normalize_response(raw)
        self.assertEqual(len(calls), 1)
        self.assertEqual(req.reasoning, 0.125)
        self.assertEqual(req.confidence, 0.75)


if __name__ == "__main__":
    unittest.main()

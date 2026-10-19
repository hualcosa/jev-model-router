from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from router_core.contracts import ProviderResult, ProviderStatus, TaskRequirements
from router_core.privacy import SYNTHETIC_SMOKE
from scripts.spikes import measure_overhead as probe


class OverheadMeasurementTests(unittest.TestCase):
    def test_nearest_rank_null_empty_and_invalid_timing(self):
        self.assertEqual(probe.distribution([]), {"n": 0, "p50_ms": None, "p95_ms": None})
        self.assertEqual(probe.distribution([20, 1, 3, 4])["p50_ms"], 3)
        self.assertEqual(probe.distribution([20, 1, 3, 4])["p95_ms"], 20)
        for values in ([float('nan')], [float('inf')], [True]):
            with self.assertRaises(ValueError):
                probe.distribution(values)
        # Paired differences may be negative; never clamp a noisy measurement.
        self.assertEqual(probe.distribution([-2, -1])["p50_ms"], -2)

    def test_local_arms_real_state_logging_dedupe_no_key_or_service(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(probe, "load_private_key", side_effect=AssertionError("key forbidden")), \
                patch.object(probe, "JevClient", side_effect=AssertionError("network forbidden")):
            result = probe.local_measurements(Path(directory).resolve(), 2)
        self.assertEqual(result["external_calls"], 0)
        self.assertEqual(len(result["summaries"]), 12)
        self.assertEqual(len(result["samples"]), 24)
        for label, summary in result["summaries"].items():
            enabled = ":disabled:" not in label
            self.assertEqual(summary["callback_attempts"], 2 if enabled else 0)
            self.assertEqual(summary["warning_count"], 2 if ":warn:" in label else 0)
            self.assertEqual(summary["continuation_events"], 8)
            self.assertEqual(summary["continuation_callback_attempts"], 0)
            self.assertEqual(summary["duplicate_callback_attempts"], 0)
            if enabled and "log=True" in label:
                self.assertGreater(summary["retained_telemetry_rows"], 0)
            else:
                self.assertEqual(summary["telemetry_file_bytes"], [0, 0, 0])
        # Reverse alternating arms so a uniform fixed first-run advantage is
        # not confused with logging cost. Both samples contain full traces.
        self.assertEqual(result["samples"][0]["arm"], result["samples"][-1]["arm"])
        for sample in result["samples"]:
            self.assertEqual(len(sample["timings"]), 9)
            self.assertAlmostEqual(sum(t["elapsed_ms"] for t in sample["timings"]), sample["total_ms"])

    def test_live_uses_only_shipped_description_retains_failures_and_no_retries(self):
        results = [ProviderResult(ProviderStatus.SUCCESS, TaskRequirements(0, 0, 0, .9, "T0", risk="low")),
                   ProviderResult(ProviderStatus.FAILURE, reason_code="timeout")]
        calls = []
        class Client:
            deadline_ms = 2500
            def __init__(self, **kwargs):
                pass
            def classify(self, description):
                calls.append(description.provider_state())
                return results.pop(0)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(probe, "load_private_key", return_value="opaque-fixture") as key, \
                patch.object(probe, "JevClient", Client):
            result = probe.live_measurements(Path(directory).resolve(), 2, Path("/fixture/key"))
        key.assert_called_once_with(Path("/fixture/key"))
        self.assertEqual(calls, [{"task_summary": SYNTHETIC_SMOKE}]*2)
        self.assertEqual(result["callback_attempts"], 2)
        self.assertEqual(result["client_results"], {"success": 1, "failure": 1})
        self.assertEqual(result["client_wall_latency_all_results"]["n"], 2)
        self.assertEqual(result["client_wall_latency_success_only"]["n"], 1)
        self.assertEqual(result["continuation_callback_attempts"], 0)
        self.assertEqual(result["duplicate_callback_attempts"], 0)
        self.assertEqual(result["samples"][1]["provider"]["reason_code"], "timeout")

    def test_live_consent_flags_required_together_before_any_key_access(self):
        for arguments in (["--live-synthetic"], ["--key-file", "/fixture/key"]):
            with patch.object(probe, "load_private_key") as key, self.assertRaises(SystemExit):
                probe.main(arguments)
            key.assert_not_called()


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Audit the pinned official SDK. Offline by default; never sends project text.

Run in a private venv containing typesafe-sdk==0.7.5. The live switch permits
only the hardcoded synthetic task below and still requires TYPESAFE_API_KEY.
An offline response validates the SDK contract, NOT service behavior/latency.
"""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

SYNTHETIC_TASK = "List the names of three imaginary files: alpha.py, beta.py, gamma.py."
TIERS = {"T0": "Mechanical lookup", "T1": "Standard implementation", "T2": "Difficult reasoning",
         "T3": "Exceptional frontier reasoning", "abstain": "Insufficient information"}


# Share the production reader; launcher path is trusted, never project input.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from router_core.credentials import load_private_key


def run(live=False):
    record = {"sdk": "typesafe-sdk", "expected_version": "0.7.5",
              "mode": "live_synthetic" if live else "offline_mock_transport",
              "network_request": False}
    if live and not os.environ.get("TYPESAFE_API_KEY"):
        return {**record, "status": "blocked_missing_key", "credential_env": "TYPESAFE_API_KEY"}, 2
    try:
        from typesafe_sdk import Choice, Score, TypeSafeClient, RetryPolicy
        import httpx2
        record["installed_version"] = importlib.metadata.version("typesafe-sdk")
    except ImportError:
        return {**record, "status": "blocked_missing_sdk"}, 2
    if record["installed_version"] != record["expected_version"]:
        return {**record, "status": "blocked_sdk_version_mismatch"}, 2

    calls = []

    def mock(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["state"] == {"task_summary": SYNTHETIC_TASK}
        assert str(request.url) == "https://api.typesafe.ai/v1/systemone"
        return httpx2.Response(200, json={
            "answers": {
                "tier": {"type": "choice", "choice": "T0", "confidence": 0.94,
                         "probabilities": {"T0": 0.94, "T1": 0.02, "T2": 0.02,
                                           "T3": 0.01, "abstain": 0.01}},
                "reasoning": {"type": "score", "score": 0.25, "confidence": 0.92,
                              "legend": {"0": "Low", "1": "Medium", "2": "High"},
                              "probabilities": {"0": 0.75, "1": 0.25, "2": 0.0}},
            }, "model": "jev-latest", "usage": {"input_tokens": 10, "output_tokens": 5}})

    options = {"timeout": 2.0, "retry": RetryPolicy(max_retries=0), "compression": False}
    if not live:
        options.update(api_key="synthetic-test-key", transport=httpx2.MockTransport(mock))
    start = time.monotonic()
    try:
        with TypeSafeClient(**options) as client:
            record["network_request"] = live
            result = client.system_one(
                state={"task_summary": SYNTHETIC_TASK},
                questions={"tier": Choice(instructions="Classify required task capability, not a model.",
                                          criteria=TIERS),
                           "reasoning": Score(criteria=["Low", "Medium", "High"])})
        choice, score = result.choices["tier"], result.scores["reasoning"]
        assert choice.choice in TIERS
        assert 0 <= choice.confidence <= 1 and 0 <= score.confidence <= 1
        assert 0 <= score.score <= 2
        record.update(status="passed", selected_tier=choice.choice,
                      tier_confidence=choice.confidence, reasoning_score=score.score,
                      reasoning_confidence=score.confidence,
                      request_count=1 if live else len(calls),
                      model=result.model,
                      elapsed_ms=round((time.monotonic() - start) * 1000, 2),
                      evidence="live_service" if live else "official_sdk_mock_contract_only")
        return record, 0
    except Exception as error:
        # Provider exceptions can contain payloads/URLs; log type only, never text.
        return {**record, "status": "failed", "error_type": type(error).__name__,
                "elapsed_ms": round((time.monotonic() - start) * 1000, 2)}, 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-synthetic", action="store_true")
    parser.add_argument("--env-file", type=Path, help="private file containing only TYPESAFE_API_KEY=...")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.env_file and not args.live_synthetic:
        parser.error("--env-file is only read with explicit --live-synthetic")
    if args.env_file:
        try:
            os.environ["TYPESAFE_API_KEY"] = load_private_key(args.env_file)
        except (OSError, ValueError, UnicodeError):
            print(json.dumps({"status": "blocked_invalid_credential_file", "network_request": False}))
            return 2
    record, code = run(args.live_synthetic)
    rendered = json.dumps(record, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as file:
            file.write(rendered)
    print(rendered, end="")
    return code


if __name__ == "__main__":
    sys.exit(main())

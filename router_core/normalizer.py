"""Strict normalization of the SDK worker's small response contract.

Scores use an explicit three-point rubric (0..2), not probabilities. Confidence
is provider-reported uncertainty, never estimated task-success probability.
"""
import math

from .contracts import RiskLevel, TaskRequirements, TaskTier


def _object(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError("invalid_provider_schema")
    return value


def _number(value, upper=1):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid_provider_score")
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise ValueError("invalid_provider_score") from None
    if not math.isfinite(number) or not 0 <= number <= upper:
        raise ValueError("invalid_provider_score")
    return number


def normalize_response(raw):
    """Require all queried answers; incomplete success is a failure, not T0."""
    _object(raw, ("schema_version", "tier", "risk", "complexity", "reasoning", "tool_complexity"))
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError("invalid_provider_schema")
    values, confidence = {}, []
    for name in ("tier", "risk"):
        answer = _object(raw[name], ("choice", "confidence"))
        # Validate enums before constructing exceptions with untrusted values.
        enum = TaskTier if name == "tier" else RiskLevel
        if not isinstance(answer["choice"], str) or answer["choice"] not in {e.value for e in enum}:
            raise ValueError("invalid_provider_choice")
        values[name] = enum(answer["choice"])
        confidence.append(_number(answer["confidence"]))
    for name in ("complexity", "reasoning", "tool_complexity"):
        answer = _object(raw[name], ("score", "confidence"))
        values[name] = _number(answer["score"], 2) / 2
        confidence.append(_number(answer["confidence"]))
    return TaskRequirements(**values, confidence=min(confidence),
                            provider_raw_tier=values["tier"].value)

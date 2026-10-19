"""Immutable, strictly validated contracts shared by router runtimes.

These types define data shape only. They deliberately contain no classification,
policy, catalog, persistence, or adapter behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import math
from typing import Any, Dict, Mapping, Optional, Type, TypeVar

SCHEMA_VERSION = 1
MAX_ID_LENGTH = 256
MAX_TEXT_LENGTH = 100_000
MAX_LABEL_LENGTH = 256


class _StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class Runtime(_StringEnum):
    CLAUDE = "claude"
    CODEX = "codex"


class EventKind(_StringEnum):
    ROOT_PROMPT = "root_prompt"
    SUBAGENT_SPAWN = "subagent_spawn"
    PREFLIGHT = "preflight"
    PREPARED_TASK = "prepared_task"


class TaskBinding(_StringEnum):
    ORCHESTRATOR_ATTESTED = "orchestrator_attested"
    NATIVE_PLAINTEXT = "native_plaintext"
    UNKNOWN = "unknown"


class RiskLevel(_StringEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskTier(_StringEnum):
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    ABSTAIN = "abstain"


class ProviderStatus(_StringEnum):
    SUCCESS = "success"
    UNAVAILABLE = "unavailable"
    FAILURE = "failure"


class RouteDisposition(_StringEnum):
    SKIP = "skip"
    DEFER = "defer"
    WARN_ROOT = "warn_root"
    ROUTE_WORKER = "route_worker"


def _mapping(value: Any, name: str, fields: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{name} field names must be strings")
    unknown = set(value) - fields
    missing = fields.intersection(_REQUIRED_FIELDS.get(name, set())) - set(value)
    if unknown:
        raise ValueError(f"{name} contains unknown field(s): {', '.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"{name} is missing required field(s): {', '.join(sorted(missing))}")
    return value


_REQUIRED_FIELDS: Dict[str, set[str]] = {
    "TaskEnvelope": {"runtime", "event", "session_id", "task_id", "task_text", "has_custom_or_unknown_profile"},
    "TaskRequirements": {"complexity", "reasoning", "tool_complexity", "confidence", "tier"},
    "ProviderResult": {"status"},
    "RouteDecision": {"disposition", "reason_code", "version", "event"},
}


def _enum(enum_type: Type[_StringEnum], value: Any, name: str) -> Any:
    if isinstance(value, enum_type):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"invalid {name}: {value!r}") from exc


def _string(value: Any, name: str, *, required: bool = False, max_length: int = MAX_LABEL_LENGTH,
            allow_empty: bool = False) -> Optional[str]:
    if value is None:
        if required:
            raise ValueError(f"{name} must be a string")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string or null")
    if len(value) > max_length:
        raise ValueError(f"{name} exceeds maximum length {max_length}")
    if required and not value.strip():
        raise ValueError(f"{name} must not be empty")
    if not allow_empty and value == "":
        raise ValueError(f"{name} must not be empty")
    return value


def _score(value: Any, name: str, *, optional: bool = False) -> Optional[float]:
    if value is None and optional:
        return None
    # bool is an int subclass, so reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number between 0 and 1")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be a finite number between 0 and 1")
    return number


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _versioned(data: Any, name: str, fields: set[str]) -> Mapping[str, Any]:
    obj = _mapping(data, name, fields | {"schema_version"})
    version = obj.get("schema_version")
    if type(version) is not int or version != SCHEMA_VERSION:
        raise ValueError(f"unsupported {name} schema_version: {version!r}")
    return obj


T = TypeVar("T")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _json_loads(value: str) -> Any:
    if not isinstance(value, str):
        raise ValueError("JSON input must be a string")
    try:
        # Reject NaN and Infinity, which Python's default decoder otherwise accepts.
        return json.loads(value, object_pairs_hook=_unique_object, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(f"invalid JSON number: {token}")))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid JSON") from exc


class _JsonContract:
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls: Type[T], value: str) -> T:
        return cls.from_dict(_json_loads(value))  # type: ignore[attr-defined,no-any-return]


@dataclass(frozen=True)
class TaskEnvelope(_JsonContract):
    runtime: Runtime
    event: EventKind
    session_id: str
    task_id: str
    task_text: str
    has_custom_or_unknown_profile: bool
    turn_id: Optional[str] = None
    tool_call_id: Optional[str] = None
    decision_reference: Optional[str] = None
    task_binding: TaskBinding = TaskBinding.UNKNOWN
    active_root_model: Optional[str] = None
    active_root_effort: Optional[str] = None
    explicit_model: Optional[str] = None
    explicit_effort: Optional[str] = None
    explicit_agent_type: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "runtime", _enum(Runtime, self.runtime, "runtime"))
        object.__setattr__(self, "event", _enum(EventKind, self.event, "event"))
        object.__setattr__(self, "task_binding", _enum(TaskBinding, self.task_binding, "task_binding"))
        for field in ("session_id", "task_id"):
            object.__setattr__(self, field, _string(getattr(self, field), field, required=True, max_length=MAX_ID_LENGTH))
        if not isinstance(self.task_text, str):
            raise ValueError("task_text must be a string")
        if len(self.task_text) > MAX_TEXT_LENGTH:
            raise ValueError(f"task_text exceeds maximum length {MAX_TEXT_LENGTH}")
        object.__setattr__(self, "has_custom_or_unknown_profile", _bool(self.has_custom_or_unknown_profile, "has_custom_or_unknown_profile"))
        for field in ("turn_id", "tool_call_id", "decision_reference"):
            object.__setattr__(self, field, _string(getattr(self, field), field, max_length=MAX_ID_LENGTH))
        for field in ("active_root_model", "active_root_effort", "explicit_agent_type"):
            object.__setattr__(self, field, _string(getattr(self, field), field, allow_empty=True))
        # None means absent; an empty string is intentionally a present explicit pin.
        for field in ("explicit_model", "explicit_effort"):
            object.__setattr__(self, field, _string(getattr(self, field), field, allow_empty=True))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "runtime": self.runtime.value,
            "event": self.event.value,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "task_text": self.task_text,
            "has_custom_or_unknown_profile": self.has_custom_or_unknown_profile,
            "turn_id": self.turn_id,
            "tool_call_id": self.tool_call_id,
            "decision_reference": self.decision_reference,
            "task_binding": self.task_binding.value,
            "active_root_model": self.active_root_model,
            "active_root_effort": self.active_root_effort,
            "explicit_model": self.explicit_model,
            "explicit_effort": self.explicit_effort,
            "explicit_agent_type": self.explicit_agent_type,
        }

    def safe_telemetry(self) -> Dict[str, Any]:
        """Return envelope metadata without task text or contextual prose."""
        # Input strings (including pins, IDs, profile and opaque references) can
        # contain arbitrary user content. Do not log them through a safe helper.
        return {
            "schema_version": SCHEMA_VERSION,
            "runtime": self.runtime.value,
            "event": self.event.value,
            "task_binding": self.task_binding.value,
            "has_custom_or_unknown_profile": self.has_custom_or_unknown_profile,
            "has_model_pin": self.explicit_model is not None,
            "has_effort_pin": self.explicit_effort is not None,
            "has_decision_reference": self.decision_reference is not None,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "TaskEnvelope":
        fields = {"runtime", "event", "session_id", "task_id", "task_text", "has_custom_or_unknown_profile",
                  "turn_id", "tool_call_id", "decision_reference", "task_binding", "active_root_model",
                  "active_root_effort", "explicit_model", "explicit_effort", "explicit_agent_type"}
        obj = _versioned(data, "TaskEnvelope", fields)
        return cls(**{key: obj[key] for key in fields if key in obj})


@dataclass(frozen=True)
class TaskRequirements(_JsonContract):
    complexity: float
    reasoning: float
    tool_complexity: float
    confidence: float
    tier: TaskTier
    ambiguity: Optional[float] = None
    risk: Optional[RiskLevel] = None
    provider_raw_tier: Optional[str] = None

    def __post_init__(self) -> None:
        for field in ("complexity", "reasoning", "tool_complexity", "confidence"):
            object.__setattr__(self, field, _score(getattr(self, field), field))
        object.__setattr__(self, "ambiguity", _score(self.ambiguity, "ambiguity", optional=True))
        object.__setattr__(self, "tier", _enum(TaskTier, self.tier, "tier"))
        if self.risk is not None:
            object.__setattr__(self, "risk", _enum(RiskLevel, self.risk, "risk"))
        object.__setattr__(self, "provider_raw_tier", _string(self.provider_raw_tier, "provider_raw_tier"))

    def to_dict(self) -> Dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "complexity": self.complexity, "reasoning": self.reasoning,
                "tool_complexity": self.tool_complexity, "confidence": self.confidence, "tier": self.tier.value,
                "ambiguity": self.ambiguity, "risk": self.risk.value if self.risk else None,
                "provider_raw_tier": self.provider_raw_tier}

    @classmethod
    def from_dict(cls, data: Any) -> "TaskRequirements":
        fields = {"complexity", "reasoning", "tool_complexity", "confidence", "tier", "ambiguity", "risk", "provider_raw_tier"}
        obj = _versioned(data, "TaskRequirements", fields)
        return cls(**{key: obj[key] for key in fields if key in obj})


@dataclass(frozen=True)
class ProviderResult(_JsonContract):
    status: ProviderStatus
    requirements: Optional[TaskRequirements] = None
    provider: Optional[str] = None
    reason_code: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", _enum(ProviderStatus, self.status, "status"))
        if self.requirements is not None and not isinstance(self.requirements, TaskRequirements):
            raise ValueError("requirements must be TaskRequirements or null")
        if self.status is ProviderStatus.SUCCESS and self.requirements is None:
            raise ValueError("successful provider result requires requirements")
        if self.status is not ProviderStatus.SUCCESS and self.requirements is not None:
            raise ValueError("unavailable or failed provider result cannot contain requirements")
        object.__setattr__(self, "provider", _string(self.provider, "provider"))
        object.__setattr__(self, "reason_code", _string(self.reason_code, "reason_code"))

    def to_dict(self) -> Dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "status": self.status.value,
                "requirements": self.requirements.to_dict() if self.requirements else None,
                "provider": self.provider, "reason_code": self.reason_code}

    @classmethod
    def from_dict(cls, data: Any) -> "ProviderResult":
        fields = {"status", "requirements", "provider", "reason_code"}
        obj = _versioned(data, "ProviderResult", fields)
        requirements = obj.get("requirements")
        return cls(status=obj["status"], requirements=TaskRequirements.from_dict(requirements) if requirements is not None else None,
                   provider=obj.get("provider"), reason_code=obj.get("reason_code"))


@dataclass(frozen=True)
class RouteDecision(_JsonContract):
    disposition: RouteDisposition
    reason_code: str
    version: str
    event: EventKind
    selected_model: Optional[str] = None
    selected_effort: Optional[str] = None
    recommended_model: Optional[str] = None
    recommended_effort: Optional[str] = None
    confidence: Optional[float] = None
    provenance: Optional[str] = None
    catalog_source: Optional[str] = None
    snapshot_version: Optional[str] = None
    catalog_version: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "disposition", _enum(RouteDisposition, self.disposition, "disposition"))
        object.__setattr__(self, "event", _enum(EventKind, self.event, "event"))
        for field in ("reason_code", "version"):
            object.__setattr__(self, field, _string(getattr(self, field), field, required=True))
        for field in ("selected_model", "selected_effort", "recommended_model", "recommended_effort", "provenance", "catalog_source"):
            object.__setattr__(self, field, _string(getattr(self, field), field))
        object.__setattr__(self, "confidence", _score(self.confidence, "confidence", optional=True))
        for field in ("snapshot_version", "catalog_version"):
            value = getattr(self, field)
            if value is not None and (not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value)):
                raise ValueError("invalid decision snapshot version")
        if (self.snapshot_version is None) != (self.catalog_version is None):
            raise ValueError("decision snapshot versions must be paired")
        if self.disposition is RouteDisposition.ROUTE_WORKER:
            if self.event not in (EventKind.SUBAGENT_SPAWN, EventKind.PREPARED_TASK):
                raise ValueError("route_worker is only valid for worker task events")
            if self.selected_model is None:
                raise ValueError("route_worker requires selected_model")
        elif self.selected_model is not None or self.selected_effort is not None:
            raise ValueError("selected route fields are only valid for route_worker")
        if self.disposition is RouteDisposition.WARN_ROOT and self.event not in (EventKind.ROOT_PROMPT, EventKind.PREFLIGHT):
            raise ValueError("warn_root is only valid for root_prompt or preflight")
        if self.disposition is RouteDisposition.WARN_ROOT and self.selected_model is not None:
            raise ValueError("root decisions may recommend but never select a model")

    def to_dict(self) -> Dict[str, Any]:
        data = {"schema_version": SCHEMA_VERSION, "disposition": self.disposition.value,
                "reason_code": self.reason_code, "version": self.version, "event": self.event.value,
                "selected_model": self.selected_model, "selected_effort": self.selected_effort,
                "recommended_model": self.recommended_model, "recommended_effort": self.recommended_effort,
                "confidence": self.confidence, "provenance": self.provenance, "catalog_source": self.catalog_source}
        # Omit absent additions so historical schema-v1 state roundtrips exactly.
        if self.snapshot_version is not None:
            data.update(snapshot_version=self.snapshot_version, catalog_version=self.catalog_version)
        return data

    @classmethod
    def from_dict(cls, data: Any) -> "RouteDecision":
        fields = {"disposition", "reason_code", "version", "event", "selected_model", "selected_effort",
                  "recommended_model", "recommended_effort", "confidence", "provenance", "catalog_source",
                  "snapshot_version", "catalog_version"}
        obj = _versioned(data, "RouteDecision", fields)
        return cls(**{key: obj[key] for key in fields if key in obj})

"""Fail-closed, structural recognition of native child-agent creation calls.

This module has no host, provider, filesystem, or network integration. The
runtime adapter must inject a capability profile bound to verified evidence;
tool names, versions, schemas, and generic profile types are never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
import threading
from types import MappingProxyType
from typing import Any, Mapping, Optional

from .contracts import EventKind, MAX_ID_LENGTH, MAX_TEXT_LENGTH, Runtime, TaskBinding, TaskEnvelope

MAX_COPY_BYTES = 200_000
MAX_TRACKED_EVENTS = 4096
_ALLOWED_FIELD_TYPES = frozenset({"string", "boolean", "integer", "number", "null"})
_CLAUDE_TOOLS = frozenset({"Agent", "Task"})
_CODEX_TOOLS = frozenset({"spawn_agent", "collaboration.spawn_agent", "collaborationspawn_agent"})


class SpawnStatus(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    ABSTAIN = "abstain"
    ELIGIBLE = "eligible"
    PREPARED_TASK_REQUIRED = "prepared_task_required"
    DUPLICATE = "duplicate"
    PINNED = "pinned"
    CUSTOM_PROFILE = "custom_profile"


class TrackerClaim(str, Enum):
    CLAIMED = "claimed"
    DUPLICATE = "duplicate"
    FULL = "full"


@dataclass(frozen=True)
class SpawnToolSchema:
    """One exact, externally verified native tool schema.

    `argument_fields` must describe the supported schema for this tool and
    host version. Only `task_field` supplies task plaintext. Codex-like opaque
    inputs use `plaintext_task=False` and are recognized without interpretation.
    """

    argument_fields: frozenset[str]
    task_field: str
    field_types: Mapping[str, frozenset[str]]
    pin_fields: frozenset[str] = frozenset({"model", "effort", "reasoning_effort"})
    agent_type_field: Optional[str] = None
    generic_agent_types: frozenset[str] = frozenset()
    plaintext_task: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.argument_fields, frozenset) or not self.argument_fields:
            raise ValueError("invalid_argument_schema")
        if any(not _valid_label(name) for name in self.argument_fields):
            raise ValueError("invalid_argument_schema")
        if self.task_field not in self.argument_fields or not _valid_label(self.task_field):
            raise ValueError("invalid_task_field")
        if not isinstance(self.pin_fields, frozenset) or any(not _valid_label(name) for name in self.pin_fields):
            raise ValueError("invalid_pin_schema")
        if self.task_field in self.pin_fields:
            raise ValueError("task_field_cannot_be_pin")
        if not isinstance(self.field_types, Mapping) or set(self.field_types) != set(self.argument_fields):
            raise ValueError("invalid_argument_types")
        normalized_types = {}
        for name, types in self.field_types.items():
            if not _valid_label(name) or not isinstance(types, frozenset) or not types:
                raise ValueError("invalid_argument_types")
            if not types.issubset(_ALLOWED_FIELD_TYPES):
                raise ValueError("unknown_argument_type")
            normalized_types[name] = types
        if self.field_types.get(self.task_field) != frozenset({"string"}):
            raise ValueError("task_field_must_be_string")
        if self.agent_type_field is not None and self.field_types.get(self.agent_type_field) != frozenset({"string"}):
            raise ValueError("agent_type_field_must_be_string")
        object.__setattr__(self, "field_types", MappingProxyType(normalized_types))
        if self.agent_type_field is not None and (
            not _valid_label(self.agent_type_field) or self.agent_type_field not in self.argument_fields
        ):
            raise ValueError("invalid_agent_type_field")
        if not isinstance(self.generic_agent_types, frozenset) or any(
            not _valid_label(name) for name in self.generic_agent_types
        ):
            raise ValueError("invalid_generic_types")
        if type(self.plaintext_task) is not bool:
            raise ValueError("invalid_plaintext_capability")


@dataclass(frozen=True)
class CapabilityProfile:
    """Trusted, version-bound host evidence supplied by the runtime adapter."""

    runtime: Runtime
    surface: str
    host_version: str
    input_schema_version: str
    tools: Mapping[str, SpawnToolSchema]

    def __post_init__(self) -> None:
        try:
            runtime = Runtime(self.runtime)
        except (ValueError, TypeError):
            raise ValueError("invalid_runtime") from None
        object.__setattr__(self, "runtime", runtime)
        for name in ("surface", "host_version", "input_schema_version"):
            value = getattr(self, name)
            if not _valid_label(value):
                raise ValueError("invalid_capability_profile")
        if not isinstance(self.tools, Mapping) or not self.tools:
            raise ValueError("invalid_tool_profile")
        copied = {}
        for tool_name, schema in self.tools.items():
            if not _valid_label(tool_name) or not isinstance(schema, SpawnToolSchema):
                raise ValueError("invalid_tool_profile")
            expected_tools = _CLAUDE_TOOLS if runtime is Runtime.CLAUDE else _CODEX_TOOLS
            if tool_name not in expected_tools:
                raise ValueError("unsupported_native_tool")
            if runtime is Runtime.CLAUDE and (schema.task_field != "prompt" or not schema.plaintext_task):
                raise ValueError("invalid_claude_task_capability")
            if runtime is Runtime.CODEX and (schema.task_field != "message" or schema.plaintext_task):
                raise ValueError("invalid_codex_task_capability")
            native_type_field = "subagent_type" if runtime is Runtime.CLAUDE else "agent_type"
            if (native_type_field in schema.argument_fields and schema.agent_type_field != native_type_field) or (
                    schema.agent_type_field is not None and schema.agent_type_field != native_type_field):
                raise ValueError("unprotected_agent_type_field")
            generic_types = {"general-purpose"} if runtime is Runtime.CLAUDE else {"default"}
            if not schema.generic_agent_types.issubset(generic_types):
                raise ValueError("unverified_generic_profile")
            copied[tool_name] = schema
        object.__setattr__(self, "tools", MappingProxyType(copied))


@dataclass(frozen=True)
class SpawnAssessment:
    status: SpawnStatus
    reason_code: str
    task_id: Optional[str] = None
    envelope: Optional[TaskEnvelope] = field(default=None, repr=False)
    # Original JSON-like arguments are kept only as an immutable, safe copy
    # for a future adapter. They are deliberately omitted from repr/telemetry.
    original_args: Optional[Mapping[str, Any]] = field(default=None, repr=False)
    runtime: Optional[Runtime] = None

    def safe_telemetry(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "reason_code": self.reason_code,
            "runtime": self.runtime.value if self.runtime else None,
            "has_task": self.envelope is not None,
        }

    def copy_original_args(self) -> Optional[dict[str, Any]]:
        if self.original_args is None:
            return None
        return _thaw(self.original_args)


class AssessmentTracker:
    """Process-local at-most-once tracker; not a cross-process dedupe store."""

    def __init__(self, max_entries: int = MAX_TRACKED_EVENTS) -> None:
        if type(max_entries) is not int or not 1 <= max_entries <= MAX_TRACKED_EVENTS:
            raise ValueError("invalid_tracker_capacity")
        self._max_entries = max_entries
        self._seen: set[tuple[str, str, str, str]] = set()
        self._lock = threading.Lock()

    def claim(self, key: tuple[str, str, str, str]) -> TrackerClaim:
        with self._lock:
            if key in self._seen:
                return TrackerClaim.DUPLICATE
            if len(self._seen) >= self._max_entries:
                return TrackerClaim.FULL
            self._seen.add(key)
            return TrackerClaim.CLAIMED


def assess_child_spawn(
    *,
    profile: Optional[CapabilityProfile],
    event_name: Any,
    event_schema_version: Any,
    tool_name: Any,
    tool_input: Any,
    host_version: Any,
    surface: Any,
    project_id: Any,
    session_id: Any,
    tool_use_id: Any,
    tracker: AssessmentTracker,
) -> SpawnAssessment:
    """Recognize one eligible PreToolUse child spawn, without classifying it.

    Missing identity/schema evidence and unsupported versions safely abstain.
    The profile is trusted configuration, not inferred from this event.
    """
    if not isinstance(profile, CapabilityProfile):
        return _abstain("capability_unavailable")
    if not isinstance(event_name, str) or event_name != "PreToolUse":
        return _not_applicable("not_pre_tool_use", profile.runtime)
    if not isinstance(tool_name, str):
        return _abstain("invalid_tool_name", profile.runtime)
    schema = profile.tools.get(tool_name)
    if schema is None:
        return _not_applicable("unrelated_tool", profile.runtime)

    # Pins bypass before even examining task/profile content. Non-null includes
    # the empty string: do not normalize, strip, or replace native pins.
    if isinstance(tool_input, Mapping):
        pin_fields = schema.pin_fields | frozenset({"model", "effort", "reasoning_effort"})
        if any(field_name in tool_input and tool_input[field_name] is not None for field_name in pin_fields):
            return SpawnAssessment(SpawnStatus.PINNED, "explicit_pin", runtime=profile.runtime)

    if not _bounded_context(host_version, 128) or not _bounded_context(surface, 128):
        return _abstain("missing_host_identity", profile.runtime)
    if host_version != profile.host_version or surface != profile.surface:
        return _abstain("unsupported_host_version", profile.runtime)
    if not isinstance(event_schema_version, str) or event_schema_version != profile.input_schema_version:
        return _abstain("unknown_event_schema", profile.runtime)
    if not _bounded_context(project_id, MAX_ID_LENGTH) or not _bounded_context(session_id, MAX_ID_LENGTH):
        return _abstain("missing_project_or_session", profile.runtime)
    if not _bounded_context(tool_use_id, MAX_ID_LENGTH):
        return _abstain("missing_tool_use_id", profile.runtime)
    if not isinstance(tracker, AssessmentTracker):
        return _abstain("tracker_unavailable", profile.runtime)

    key = (profile.runtime.value, project_id, session_id, tool_use_id)
    claim = tracker.claim(key)
    if claim is TrackerClaim.DUPLICATE:
        return SpawnAssessment(SpawnStatus.DUPLICATE, "duplicate_tool_use", runtime=profile.runtime)
    if claim is TrackerClaim.FULL:
        return _abstain("tracker_full", profile.runtime)

    if not isinstance(tool_input, Mapping) or any(not isinstance(key, str) for key in tool_input):
        return _abstain("invalid_tool_arguments", profile.runtime)
    if set(tool_input) - schema.argument_fields:
        return _abstain("unknown_argument_schema", profile.runtime)

    # Determine profile eligibility before touching task text or copying args.
    agent_type = None
    if schema.agent_type_field is not None and schema.agent_type_field in tool_input:
        candidate = tool_input[schema.agent_type_field]
        if not _is_type(candidate, schema.field_types[schema.agent_type_field]):
            return _abstain("unknown_agent_type", profile.runtime)
        agent_type = candidate
        if candidate not in schema.generic_agent_types:
            return SpawnAssessment(SpawnStatus.CUSTOM_PROFILE, "custom_or_unknown_profile", runtime=profile.runtime)

    for field_name, value in tool_input.items():
        allowed_types = schema.field_types.get(field_name)
        if allowed_types is None or not _is_type(value, allowed_types):
            return _abstain("unsupported_argument_type", profile.runtime)
        if isinstance(value, str) and not _valid_text(value):
            return _abstain("invalid_text_encoding", profile.runtime)

    task_text = tool_input.get(schema.task_field)
    if not isinstance(task_text, str):
        return _abstain("missing_or_nontext_task", profile.runtime)
    if not task_text.strip():
        return _abstain("empty_task", profile.runtime)
    try:
        task_size = len(task_text.encode("utf-8"))
    except UnicodeError:
        return _abstain("invalid_text_encoding", profile.runtime)
    if task_size > MAX_TEXT_LENGTH:
        return _abstain("task_too_large", profile.runtime)

    safe_args = _freeze_json(tool_input)
    if safe_args is None:
        return _abstain("unsupported_argument_type_or_copy_limit", profile.runtime)
    task_id = _stable_task_id(key)

    if not schema.plaintext_task:
        return SpawnAssessment(
            SpawnStatus.PREPARED_TASK_REQUIRED,
            "plaintext_unavailable_requires_local_preparation",
            task_id=task_id,
            original_args=safe_args,
            runtime=profile.runtime,
        )

    try:
        envelope = TaskEnvelope(
            runtime=profile.runtime,
            event=EventKind.SUBAGENT_SPAWN,
            session_id=session_id,
            task_id=task_id,
            task_text=task_text,
            has_custom_or_unknown_profile=False,
            tool_call_id=tool_use_id,
            task_binding=TaskBinding.NATIVE_PLAINTEXT,
            explicit_model=None,
            explicit_effort=None,
            explicit_agent_type=agent_type,
        )
    except (TypeError, ValueError, UnicodeError):
        return _abstain("invalid_task_envelope", profile.runtime)
    return SpawnAssessment(
        SpawnStatus.ELIGIBLE,
        "eligible_native_child",
        task_id=task_id,
        envelope=envelope,
        original_args=safe_args,
        runtime=profile.runtime,
    )


def _stable_task_id(key: tuple[str, str, str, str]) -> str:
    # Identity contains only trusted runtime/project/session/tool identifiers;
    # it never depends on task text, task_name, ciphertext, or randomness.
    material = json.dumps(key, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return "spawn-" + hashlib.sha256(material).hexdigest()


def _valid_label(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 128 and _valid_text(value)


def _bounded_context(value: Any, limit: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and _valid_text(value)


def _valid_text(value: str) -> bool:
    try:
        value.encode("utf-8")
    except UnicodeError:
        return False
    return True


def _is_type(value: Any, allowed: frozenset[str]) -> bool:
    if type(value) is str:
        return "string" in allowed
    if type(value) is bool:
        return "boolean" in allowed
    if type(value) is int:
        return "integer" in allowed or "number" in allowed
    if type(value) is float:
        return math.isfinite(value) and "number" in allowed
    return value is None and "null" in allowed


def _freeze_json(value: Any) -> Optional[Mapping[str, Any]]:
    try:
        if not isinstance(value, Mapping):
            return None
        budget = [8]  # root object overhead, even when it has no fields
        frozen = {}
        for key, child in value.items():
            if type(key) is not str:
                return None
            encoded_key = key.encode("utf-8")
            budget[0] += 8 + len(encoded_key)
            if budget[0] > MAX_COPY_BYTES:
                return None
            frozen[key] = _freeze_scalar(child, budget)
        return MappingProxyType(frozen)
    except (TypeError, ValueError, OverflowError, UnicodeError):
        return None


def _freeze_scalar(value: Any, budget: list[int]) -> Any:
    # Count every node, including empty strings and nulls. A huge integer is
    # rejected before Python's decimal conversion or an unbounded memory copy.
    budget[0] += 8
    if type(value) is str:
        encoded = value.encode("utf-8")
        budget[0] += len(encoded)
        result = value
    elif value is None or type(value) is bool:
        budget[0] += 1
        result = value
    elif type(value) is int:
        if value.bit_length() > 256:
            raise ValueError("integer_too_large")
        budget[0] += max(1, (value.bit_length() + 7) // 8)
        result = value
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError("non_finite")
        budget[0] += 8
        result = value
    else:
        raise TypeError("unsupported_type")
    if budget[0] > MAX_COPY_BYTES:
        raise ValueError("copy_too_large")
    return result


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


def _abstain(reason: str, runtime: Optional[Runtime] = None) -> SpawnAssessment:
    return SpawnAssessment(SpawnStatus.ABSTAIN, reason, runtime=runtime)


def _not_applicable(reason: str, runtime: Optional[Runtime] = None) -> SpawnAssessment:
    return SpawnAssessment(SpawnStatus.NOT_APPLICABLE, reason, runtime=runtime)

"""Immutable, evidence-backed runtime model and effort capability inventory.

This module intentionally performs no discovery. Adapters may inject an
authoritative, versioned snapshot; absent or mismatched evidence fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
import re
from typing import Any, Optional

from .contracts import Runtime


CATALOG_SCHEMA_VERSION = 1
MAX_SNAPSHOT_BYTES = 1_048_576
MAX_CATALOG_ENTRIES = 256
MAX_SUPPORTED_EFFORTS = 16
MAX_LABEL_LENGTH = 256
MAX_EVIDENCE_LENGTH = 4096
_ENTRY_FIELDS = {
    "runtime", "surface", "host_version", "family", "target_version",
    "runtime_model_id", "tool_name", "model_field", "effort_field",
    "supported_efforts", "mapping_status", "mapping_evidence",
    "mapping_provenance", "verified_at", "availability_source",
}
_AVAILABILITY_SOURCES = {"user_assumption", "entitlement_observed", "unknown"}
_MAPPING_STATUSES = {"verified", "unverified", "rejected"}
_KNOWN_TOOLS = {
    Runtime.CLAUDE: {"Agent", "Task"},
    # Host-adapted function names observed in native Codex events are accepted
    # only as exact snapshot values; lookup never normalizes these spellings.
    Runtime.CODEX: {"spawn_agent", "collaboration.spawn_agent", "collaborationspawn_agent"},
}
_EFFORT_FIELDS = {
    Runtime.CLAUDE: {None, "effort"},
    Runtime.CODEX: {None, "reasoning_effort"},
}
_REASON_CODES = {
    "target_version_unavailable", "target_version_unverified",
    "target_version_mismatch", "runtime_unverified", "surface_unverified",
    "host_version_unverified", "tool_unsupported", "model_field_unsupported",
    "effort_unsupported", "mapping_rejected", "account_availability_unknown",
    "ambiguous_mapping",
}


class CatalogError(ValueError):
    """Safe catalog validation or lookup failure (never embeds input values)."""


class CatalogUnavailable(CatalogError):
    def __init__(self, reason_code: str):
        if reason_code not in _REASON_CODES:
            raise ValueError("unknown catalog reason code")
        self.reason_code = reason_code
        super().__init__(reason_code)


def _safe_string(value: Any, field: str, *, allow_empty: bool = False, max_length: int = MAX_LABEL_LENGTH) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise CatalogError(f"invalid catalog field: {field}")
    if len(value) > max_length:
        raise CatalogError(f"invalid catalog field: {field}")
    return value


@dataclass(frozen=True, order=True)
class ModelTarget:
    """Policy identity; deliberately separate from executable runtime IDs."""

    family: str
    target_version: str

    def __post_init__(self) -> None:
        _safe_string(self.family, "family")
        _safe_string(self.target_version, "target_version")


@dataclass(frozen=True)
class CapabilityRecord:
    runtime: Runtime
    surface: str
    host_version: str
    family: str
    target_version: str
    runtime_model_id: str
    tool_name: str
    model_field: str
    effort_field: Optional[str]
    supported_efforts: tuple[str, ...]
    mapping_status: str
    mapping_evidence: str
    mapping_provenance: str
    verified_at: str
    availability_source: str = "user_assumption"
    # Verified host observations only, never alternate executable tool inputs.
    # Explicit and version/surface scoped; no prefix/family/alias guessing.
    root_model_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            runtime = self.runtime if isinstance(self.runtime, Runtime) else Runtime(self.runtime)
        except (TypeError, ValueError):
            raise CatalogError("invalid catalog field: runtime") from None
        object.__setattr__(self, "runtime", runtime)
        for field in ("surface", "host_version", "family", "target_version", "runtime_model_id", "tool_name", "model_field", "mapping_provenance", "verified_at"):
            _safe_string(getattr(self, field), field)
        _safe_string(self.mapping_evidence, "mapping_evidence", max_length=MAX_EVIDENCE_LENGTH)
        if self.effort_field is not None:
            _safe_string(self.effort_field, "effort_field")
        if self.model_field != "model":
            raise CatalogError("unsupported catalog model field")
        if self.tool_name not in _KNOWN_TOOLS[runtime]:
            raise CatalogError("unsupported catalog tool name")
        if self.effort_field not in _EFFORT_FIELDS[runtime]:
            raise CatalogError("unsupported catalog effort field")
        if type(self.supported_efforts) not in (tuple, list) or len(self.supported_efforts) > MAX_SUPPORTED_EFFORTS or any(not isinstance(item, str) or not item or len(item) > MAX_LABEL_LENGTH for item in self.supported_efforts):
            raise CatalogError("invalid catalog field: supported_efforts")
        efforts = tuple(self.supported_efforts)
        if len(set(efforts)) != len(efforts):
            raise CatalogError("duplicate supported effort")
        if self.effort_field is None and efforts:
            raise CatalogError("efforts require an effort field")
        if not isinstance(self.mapping_status, str) or self.mapping_status not in _MAPPING_STATUSES:
            raise CatalogError("invalid catalog field: mapping_status")
        if not isinstance(self.availability_source, str) or self.availability_source not in _AVAILABILITY_SOURCES:
            raise CatalogError("invalid catalog field: availability_source")
        if self.mapping_status == "verified":
            try:
                timestamp = datetime.fromisoformat(self.verified_at.replace("Z", "+00:00"))
            except ValueError:
                raise CatalogError("invalid catalog field: verified_at") from None
            if timestamp.tzinfo is None:
                raise CatalogError("invalid catalog field: verified_at")
        object.__setattr__(self, "supported_efforts", efforts)
        if type(self.root_model_ids) not in (tuple, list) or len(self.root_model_ids) > 8:
            raise CatalogError("invalid catalog field: root_model_ids")
        for value in self.root_model_ids:
            _safe_string(value, "root_model_ids")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", value):
                raise CatalogError("invalid catalog field: root_model_ids")
        if len(set(self.root_model_ids)) != len(self.root_model_ids):
            raise CatalogError("duplicate observed root identity")
        object.__setattr__(self, "root_model_ids", tuple(self.root_model_ids))

    @property
    def target(self) -> ModelTarget:
        return ModelTarget(self.family, self.target_version)


@dataclass(frozen=True)
class LookupResult:
    record: Optional[CapabilityRecord]
    reason_code: Optional[str]

    @property
    def eligible(self) -> bool:
        return self.record is not None


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CatalogError("duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise CatalogError("invalid JSON number")


@dataclass(frozen=True)
class CatalogRegistry:
    records: tuple[CapabilityRecord, ...] = ()

    def __post_init__(self) -> None:
        if type(self.records) not in (tuple, list) or len(self.records) > MAX_CATALOG_ENTRIES or any(not isinstance(item, CapabilityRecord) for item in self.records):
            raise CatalogError("records must be capability records")
        records = tuple(self.records)
        seen: set[tuple[str, str, str, str, str, str]] = set()
        ids: set[tuple[str, str, str, str, str]] = set()
        for record in records:
            key = (record.runtime.value, record.surface, record.host_version, record.family, record.target_version, record.tool_name)
            model_key = (record.runtime.value, record.surface, record.host_version, record.runtime_model_id, record.tool_name)
            if key in seen or model_key in ids:
                raise CatalogError("duplicate catalog mapping")
            seen.add(key)
            ids.add(model_key)
        object.__setattr__(self, "records", records)

    @classmethod
    def from_json(cls, raw: str) -> "CatalogRegistry":
        if not isinstance(raw, str):
            raise CatalogError("JSON input must be a string")
        try:
            if len(raw.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
                raise CatalogError("catalog snapshot exceeds size limit")
        except UnicodeEncodeError:
            raise CatalogError("invalid catalog JSON") from None
        try:
            data = json.loads(raw, object_pairs_hook=_object_pairs, parse_constant=_reject_constant)
        except CatalogError:
            raise
        except (TypeError, ValueError, RecursionError):
            raise CatalogError("invalid catalog JSON") from None
        if not isinstance(data, dict) or set(data) != {"schema_version", "entries"}:
            raise CatalogError("invalid catalog snapshot fields")
        version = data["schema_version"]
        if type(version) is not int or version != CATALOG_SCHEMA_VERSION:
            raise CatalogError("unsupported catalog schema version")
        entries = data["entries"]
        if not isinstance(entries, list) or len(entries) > MAX_CATALOG_ENTRIES:
            raise CatalogError("catalog entries must be a list")
        records = []
        for entry in entries:
            if (not isinstance(entry, dict) or set(entry) - {"root_model_ids"} != _ENTRY_FIELDS):
                raise CatalogError("invalid catalog entry fields")
            if "root_model_ids" in entry and not isinstance(entry["root_model_ids"], list):
                raise CatalogError("invalid catalog field: root_model_ids")
            if not isinstance(entry["supported_efforts"], list):
                raise CatalogError("invalid catalog field: supported_efforts")
            try:
                records.append(CapabilityRecord(**entry))
            except TypeError:
                raise CatalogError("invalid catalog entry") from None
        return cls(tuple(records))

    def to_json(self) -> str:
        entries = []
        for item in self.records:
            entry = {key: getattr(item, key) for key in _ENTRY_FIELDS}
            entry["runtime"] = item.runtime.value
            entry["supported_efforts"] = list(item.supported_efforts)
            if item.root_model_ids:
                entry["root_model_ids"] = list(item.root_model_ids)
            entries.append(entry)
        return json.dumps({"schema_version": CATALOG_SCHEMA_VERSION, "entries": entries}, allow_nan=False, sort_keys=True, separators=(",", ":"))

    def lookup(
        self, *, runtime: Runtime | str, surface: str, host_version: str,
        target: ModelTarget, effort: Optional[str], tool_name: Optional[str] = None,
        model_field: Optional[str] = None,
    ) -> LookupResult:
        """Resolve only exact verified mappings; no aliases or substitutions."""
        if not isinstance(target, ModelTarget):
            raise CatalogError("target must be a model target")
        if effort is not None and (not isinstance(effort, str) or not effort):
            raise CatalogError("effort must be a non-empty string or null")
        if not isinstance(surface, str) or not isinstance(host_version, str):
            raise CatalogError("runtime scope values must be strings")
        if tool_name is not None and not isinstance(tool_name, str):
            raise CatalogError("tool_name must be a string or null")
        if model_field is not None and not isinstance(model_field, str):
            raise CatalogError("model_field must be a string or null")
        try:
            runtime_value = runtime.value if isinstance(runtime, Runtime) else Runtime(runtime).value
        except (TypeError, ValueError):
            return LookupResult(None, "runtime_unverified")
        candidates = [item for item in self.records if item.family == target.family]
        if not candidates:
            return LookupResult(None, "target_version_unavailable")
        exact = [item for item in candidates if item.target_version == target.target_version]
        if not exact:
            return LookupResult(None, "target_version_mismatch")
        scoped_runtime = [item for item in exact if item.runtime.value == runtime_value]
        if not scoped_runtime:
            return LookupResult(None, "runtime_unverified")
        scoped_surface = [item for item in scoped_runtime if item.surface == surface]
        if not scoped_surface:
            return LookupResult(None, "surface_unverified")
        scoped_host = [item for item in scoped_surface if item.host_version == host_version]
        if not scoped_host:
            return LookupResult(None, "host_version_unverified")
        scoped_tool = scoped_host
        if tool_name is not None:
            scoped_tool = [item for item in scoped_tool if item.tool_name == tool_name]
            if not scoped_tool:
                return LookupResult(None, "tool_unsupported")
        if model_field is not None:
            scoped_tool = [item for item in scoped_tool if item.model_field == model_field]
            if not scoped_tool:
                return LookupResult(None, "model_field_unsupported")
        if len(scoped_tool) != 1:
            return LookupResult(None, "ambiguous_mapping")
        item = scoped_tool[0]
        if item.mapping_status == "rejected":
            return LookupResult(None, "mapping_rejected")
        if item.mapping_status != "verified":
            return LookupResult(None, "target_version_unverified")
        if item.availability_source == "unknown":
            return LookupResult(None, "account_availability_unknown")
        if effort is not None and (item.effort_field is None or effort not in item.supported_efforts):
            return LookupResult(None, "effort_unsupported")
        return LookupResult(item, None)

    def require(self, **kwargs: Any) -> CapabilityRecord:
        result = self.lookup(**kwargs)
        if not result.eligible:
            raise CatalogUnavailable(result.reason_code or "target_version_unavailable")
        assert result.record is not None
        return result.record

    def list_eligible(self, **scope: Any) -> tuple[tuple[CapabilityRecord, ...], tuple[tuple[ModelTarget, str], ...]]:
        """List eligible targets plus bounded exclusion reason codes."""
        targets = tuple(dict.fromkeys(record.target for record in self.records))
        eligible: list[CapabilityRecord] = []
        excluded: list[tuple[ModelTarget, str]] = []
        for target in targets:
            result = self.lookup(target=target, **scope)
            if result.record is not None:
                eligible.append(result.record)
            else:
                excluded.append((target, result.reason_code or "target_version_unavailable"))
        return tuple(eligible), tuple(excluded)

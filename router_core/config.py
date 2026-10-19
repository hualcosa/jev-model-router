"""Strict, stdlib-only configuration for the intelligent router (schema v1).

The example YAML in the product specs is conceptual. This loader deliberately
accepts JSON only, so no optional YAML parser or implicit coercions enter the
trusted configuration path. Missing files use safe defaults. Invalid present
files raise :class:`ConfigError`; runtime adapters should catch that and fail
open to native, unmodified behavior.

Global configuration is trusted user configuration. Project configuration is
an untrusted deep-override layer: it may narrow routing choices and disable
transmission, but can never grant external-consent or alter the credential
source. Root settings and privacy/safety invariants are not configurable.
Resolve runtime configuration only through :func:`load_config` or
:func:`merge_config_layers`; direct dataclass construction is not a validation
or authorization boundary.
"""

from __future__ import annotations

import json
import math
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional, Union

SCHEMA_VERSION = 1
MAX_CONFIG_BYTES = 64 * 1024
MAX_JSON_DEPTH = 16
MAX_RETRY_COUNT = 0
MIN_DEADLINE_MS = 50
MAX_DEADLINE_MS = 2500
CREDENTIAL_ENV = "TYPESAFE_API_KEY"
TARGET_VERSIONS = {
    "claude": {"sonnet": "5.5", "opus": "5.5", "fable": "5.1"},
    "codex": {"luna": "6", "terra": "6", "sol": "6.1", "astra": "6"},
}
UNVERSIONED_TARGETS = frozenset({"claude.haiku"})
_TARGET_NAMES = frozenset(UNVERSIONED_TARGETS | {
    f"{runtime}.{family}" for runtime, families in TARGET_VERSIONS.items() for family in families
})
_MODES = frozenset({"disabled", "shadow", "warn", "auto_workers"})
_RUNTIMES = frozenset(TARGET_VERSIONS)


def _freeze_targets(value: Mapping[str, Mapping[str, str]]) -> Mapping[str, Mapping[str, str]]:
    return MappingProxyType({runtime: MappingProxyType(dict(families)) for runtime, families in value.items()})


class ConfigError(ValueError):
    """Sanitized configuration error, safe to display without user data."""


@dataclass(frozen=True)
class ConsentConfig:
    synthetic_tasks: bool = False
    real_tasks: bool = False


@dataclass(frozen=True)
class ClassificationConfig:
    provider: str = "typesafe_jev"
    credential_env: str = CREDENTIAL_ENV
    deadline_ms: int = MAX_DEADLINE_MS
    retry_count: int = 0
    minimize_task_payload: bool = True
    send_full_transcript: bool = False


@dataclass(frozen=True)
class BoundaryConfig:
    root_mode: str = "hybrid_structural_and_stateful"
    unknown_boundary: str = "defer"
    classify_obvious_continuation: bool = False
    explicit_preflight_enabled: bool = True


@dataclass(frozen=True)
class RootConfig:
    preserve_model: bool = True
    preserve_effort: bool = True
    warning_enabled: bool = True
    warning_once_per_task: bool = True
    material_gain_only: bool = True


@dataclass(frozen=True)
class WorkerConfig:
    route_unpinned_only: bool = True
    preserve_custom_or_unknown_profile: bool = True
    allow_verified_generic_type: bool = True
    preserve_explicit_model: bool = True
    preserve_explicit_effort: bool = True


@dataclass(frozen=True)
class PolicyConfig:
    target_versions: Mapping[str, Mapping[str, str]] = field(
        default_factory=lambda: _freeze_targets(TARGET_VERSIONS)
    )
    enabled_targets: frozenset[str] = frozenset(
        _TARGET_NAMES
    )
    allow_implicit_version_substitution: bool = False
    require_verified_runtime_mapping: bool = True
    frontier_auto_opt_in: bool = False
    min_confidence_for_auto: float = 0.75


@dataclass(frozen=True)
class ObservabilityConfig:
    log_decisions: bool = True
    record_raw_prompt: bool = False
    private_state_permissions: bool = True


@dataclass(frozen=True)
class RouterConfig:
    schema_version: int = SCHEMA_VERSION
    mode: str = "disabled"
    consent: ConsentConfig = field(default_factory=ConsentConfig)
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)
    boundary: BoundaryConfig = field(default_factory=BoundaryConfig)
    root: RootConfig = field(default_factory=RootConfig)
    workers: WorkerConfig = field(default_factory=WorkerConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)


DEFAULT_CONFIG = RouterConfig()


def _fail(path: str, expected: str) -> None:
    raise ConfigError(f"invalid config field {path}: expected {expected}")


def _object(value: Any, path: str, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "object")
    if any(not isinstance(key, str) for key in value):
        _fail(path, "string field names")
    if set(value) - allowed:
        raise ConfigError(f"unknown config field in {path}")
    return value


def _bool(value: Any, path: str) -> bool:
    if type(value) is not bool:
        _fail(path, "boolean")
    return value


def _int(value: Any, path: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        _fail(path, f"integer from {low} to {high}")
    return value


def _float(value: Any, path: str, low: float, high: float) -> float:
    if type(value) not in (int, float) or not low <= value <= high:
        _fail(path, f"finite number from {low} to {high}")
    try:
        normalized = float(value)
    except (OverflowError, ValueError):
        _fail(path, f"finite number from {low} to {high}")
    if not math.isfinite(normalized):
        _fail(path, f"finite number from {low} to {high}")
    return normalized


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ConfigError("duplicate JSON field")
        out[key] = value
    return out


def _reject_constant(_value: str) -> None:
    raise ConfigError("non-finite JSON number")


def _check_depth(value: Any, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise ConfigError("configuration nesting exceeds limit")
    if isinstance(value, dict):
        for item in value.values():
            _check_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_depth(item, depth + 1)


def _parse_json(text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        _fail("$", "JSON text")
    if len(text) > MAX_CONFIG_BYTES:
        raise ConfigError("configuration exceeds size limit")
    try:
        encoded_length = len(text.encode("utf-8"))
    except UnicodeError:
        raise ConfigError("invalid UTF-8 configuration") from None
    if encoded_length > MAX_CONFIG_BYTES:
        raise ConfigError("configuration exceeds size limit")
    try:
        value = json.loads(text, object_pairs_hook=_pairs_no_duplicates, parse_constant=_reject_constant)
    except ConfigError:
        raise
    except (ValueError, UnicodeError, RecursionError, TypeError):
        raise ConfigError("invalid JSON configuration") from None
    if not isinstance(value, dict):
        _fail("$", "object")
    _check_depth(value)
    return value


def _validate(raw: dict[str, Any]) -> dict[str, Any]:
    top = _object(raw, "$", {"schema_version", "mode", "consent", "classification", "boundary", "root", "workers", "policy", "observability"})
    version = top.get("schema_version", SCHEMA_VERSION)
    if type(version) is not int or version != SCHEMA_VERSION:
        _fail("schema_version", "supported schema version 1")
    out: dict[str, Any] = {"schema_version": SCHEMA_VERSION}
    if "mode" in top:
        mode = top["mode"]
        if not isinstance(mode, str) or mode not in _MODES:
            _fail("mode", "disabled, shadow, warn, or auto_workers")
        out["mode"] = mode

    if "consent" in top:
        consent = _object(top["consent"], "consent", {"synthetic_tasks", "real_tasks"})
        out["consent"] = {key: _bool(value, f"consent.{key}") for key, value in consent.items()}

    if "classification" in top:
        c = _object(top["classification"], "classification", {"provider", "credential_env", "deadline_ms", "retry_count", "minimize_task_payload", "send_full_transcript"})
        result: dict[str, Any] = {}
        if "provider" in c:
            if c["provider"] != "typesafe_jev":
                _fail("classification.provider", "typesafe_jev")
            result["provider"] = c["provider"]
        if "credential_env" in c:
            if c["credential_env"] != CREDENTIAL_ENV:
                _fail("classification.credential_env", "the fixed credential environment variable")
            result["credential_env"] = CREDENTIAL_ENV
        if "deadline_ms" in c:
            result["deadline_ms"] = _int(c["deadline_ms"], "classification.deadline_ms", MIN_DEADLINE_MS, MAX_DEADLINE_MS)
        if "retry_count" in c:
            result["retry_count"] = _int(c["retry_count"], "classification.retry_count", 0, MAX_RETRY_COUNT)
        if "minimize_task_payload" in c:
            result["minimize_task_payload"] = _bool(c["minimize_task_payload"], "classification.minimize_task_payload")
            if not result["minimize_task_payload"]:
                _fail("classification.minimize_task_payload", "true")
        if "send_full_transcript" in c:
            result["send_full_transcript"] = _bool(c["send_full_transcript"], "classification.send_full_transcript")
            if result["send_full_transcript"]:
                _fail("classification.send_full_transcript", "false")
        out["classification"] = result

    if "boundary" in top:
        b = _object(top["boundary"], "boundary", {"root_mode", "unknown_boundary", "classify_obvious_continuation", "explicit_preflight_enabled"})
        result = {}
        enums = {"root_mode": {"hybrid_structural_and_stateful"}, "unknown_boundary": {"defer"}}
        for key, allowed in enums.items():
            if key in b:
                if not isinstance(b[key], str) or b[key] not in allowed:
                    _fail(f"boundary.{key}", "supported safe value")
                result[key] = b[key]
        for key in ("classify_obvious_continuation", "explicit_preflight_enabled"):
            if key in b:
                result[key] = _bool(b[key], f"boundary.{key}")
                if key == "classify_obvious_continuation" and result[key]:
                    _fail(f"boundary.{key}", "false")
        out["boundary"] = result

    invariant_values = {
        "root": {"preserve_model": True, "preserve_effort": True},
        "workers": {"route_unpinned_only": True, "preserve_custom_or_unknown_profile": True, "preserve_explicit_model": True, "preserve_explicit_effort": True},
        "observability": {"record_raw_prompt": False, "private_state_permissions": True},
    }
    allowed_groups = {
        "root": {"preserve_model", "preserve_effort", "warning_enabled", "warning_once_per_task", "material_gain_only"},
        "workers": {"route_unpinned_only", "preserve_custom_or_unknown_profile", "allow_verified_generic_type", "preserve_explicit_model", "preserve_explicit_effort"},
        "observability": {"log_decisions", "record_raw_prompt", "private_state_permissions"},
    }
    invariant_values["root"].update({"warning_once_per_task": True, "material_gain_only": True})
    for group, allowed in allowed_groups.items():
        if group not in top:
            continue
        obj = _object(top[group], group, allowed)
        result = {}
        for key, value in obj.items():
            result[key] = _bool(value, f"{group}.{key}")
            if key in invariant_values[group] and result[key] is not invariant_values[group][key]:
                expected = "true" if invariant_values[group][key] else "false"
                _fail(f"{group}.{key}", expected)
        out[group] = result

    if "policy" in top:
        p = _object(top["policy"], "policy", {"target_versions", "enabled_targets", "allow_implicit_version_substitution", "require_verified_runtime_mapping", "frontier_auto_opt_in", "min_confidence_for_auto"})
        result = {}
        if "target_versions" in p:
            tv = _object(p["target_versions"], "policy.target_versions", set(_RUNTIMES))
            checked: dict[str, dict[str, str]] = {}
            for runtime, families in tv.items():
                if runtime not in _RUNTIMES:
                    _fail("policy.target_versions", "known runtime names")
                families = _object(families, f"policy.target_versions.{runtime}", set(TARGET_VERSIONS[runtime]))
                checked[runtime] = {}
                for family, version_value in families.items():
                    if not isinstance(version_value, str) or version_value != TARGET_VERSIONS[runtime][family]:
                        _fail(f"policy.target_versions.{runtime}.{family}", "the pinned desired version")
                    checked[runtime][family] = version_value
            result["target_versions"] = checked
        if "enabled_targets" in p:
            targets = p["enabled_targets"]
            if not isinstance(targets, list) or len(targets) > len(_TARGET_NAMES) or any(not isinstance(t, str) for t in targets) or len(set(targets)) != len(targets):
                _fail("policy.enabled_targets", "a unique list of known targets")
            if any(t not in _TARGET_NAMES for t in targets):
                _fail("policy.enabled_targets", "known target names")
            result["enabled_targets"] = targets
        for key in ("allow_implicit_version_substitution", "require_verified_runtime_mapping", "frontier_auto_opt_in"):
            if key in p:
                result[key] = _bool(p[key], f"policy.{key}")
                if key == "allow_implicit_version_substitution" and result[key]:
                    _fail(f"policy.{key}", "false")
                if key == "require_verified_runtime_mapping" and not result[key]:
                    _fail(f"policy.{key}", "true")
        if "min_confidence_for_auto" in p:
            result["min_confidence_for_auto"] = _float(p["min_confidence_for_auto"], "policy.min_confidence_for_auto", 0, 1)
        out["policy"] = result
    return out


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _enforce_project_restrictions(global_layer: Mapping[str, Any], project_layer: Mapping[str, Any]) -> None:
    """Reject project overrides that widen permissions or routing authority."""
    mode_rank = {"disabled": 0, "shadow": 1, "warn": 2, "auto_workers": 3}
    global_mode = global_layer.get("mode", "disabled")
    if "mode" in project_layer and mode_rank[project_layer["mode"]] > mode_rank[global_mode]:
        raise ConfigError("project config cannot enable a broader router mode")

    global_classification = global_layer.get("classification", {})
    project_classification = project_layer.get("classification", {})
    if project_classification.get("deadline_ms", MIN_DEADLINE_MS) > global_classification.get("deadline_ms", MAX_DEADLINE_MS):
        raise ConfigError("project config cannot increase the classification deadline")

    global_policy = global_layer.get("policy", {})
    project_policy = project_layer.get("policy", {})
    if "enabled_targets" in project_policy:
        global_targets = set(global_policy.get("enabled_targets", _TARGET_NAMES))
        if not set(project_policy["enabled_targets"]).issubset(global_targets):
            raise ConfigError("project config cannot enable additional targets")
    if project_policy.get("frontier_auto_opt_in", False) and not global_policy.get("frontier_auto_opt_in", False):
        raise ConfigError("project config cannot grant frontier opt-in")
    if project_policy.get("min_confidence_for_auto", global_policy.get("min_confidence_for_auto", 0.75)) < global_policy.get("min_confidence_for_auto", 0.75):
        raise ConfigError("project config cannot lower the automatic-route confidence threshold")

    boolean_restrictions = (
        ("boundary", "explicit_preflight_enabled"),
        ("root", "warning_enabled"),
        ("workers", "allow_verified_generic_type"),
        ("observability", "log_decisions"),
    )
    for section, key in boolean_restrictions:
        if project_layer.get(section, {}).get(key) is True and global_layer.get(section, {}).get(key, _default_dict()[section][key]) is False:
            raise ConfigError(f"project config cannot enable {section}.{key}")


def _freeze_config(raw: dict[str, Any]) -> RouterConfig:
    cfg = _deep_merge(_default_dict(), raw)
    policy = cfg["policy"]
    available_targets = UNVERSIONED_TARGETS | {f"{runtime}.{family}" for runtime, families in policy["target_versions"].items() for family in families}
    if not set(policy["enabled_targets"]).issubset(available_targets):
        raise ConfigError("enabled target is missing its pinned desired version")
    versions = _freeze_targets(policy["target_versions"])
    return RouterConfig(
        mode=cfg["mode"],
        consent=ConsentConfig(**cfg["consent"]),
        classification=ClassificationConfig(**cfg["classification"]),
        boundary=BoundaryConfig(**cfg["boundary"]),
        root=RootConfig(**cfg["root"]),
        workers=WorkerConfig(**cfg["workers"]),
        policy=PolicyConfig(
            target_versions=versions,
            enabled_targets=frozenset(policy["enabled_targets"]),
            allow_implicit_version_substitution=policy["allow_implicit_version_substitution"],
            require_verified_runtime_mapping=policy["require_verified_runtime_mapping"],
            frontier_auto_opt_in=policy["frontier_auto_opt_in"],
            min_confidence_for_auto=policy["min_confidence_for_auto"],
        ),
        observability=ObservabilityConfig(**cfg["observability"]),
    )


def _default_dict() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "disabled",
        "consent": {"synthetic_tasks": False, "real_tasks": False},
        "classification": {"provider": "typesafe_jev", "credential_env": CREDENTIAL_ENV, "deadline_ms": 2500, "retry_count": 0, "minimize_task_payload": True, "send_full_transcript": False},
        "boundary": {"root_mode": "hybrid_structural_and_stateful", "unknown_boundary": "defer", "classify_obvious_continuation": False, "explicit_preflight_enabled": True},
        "root": {"preserve_model": True, "preserve_effort": True, "warning_enabled": True, "warning_once_per_task": True, "material_gain_only": True},
        "workers": {"route_unpinned_only": True, "preserve_custom_or_unknown_profile": True, "allow_verified_generic_type": True, "preserve_explicit_model": True, "preserve_explicit_effort": True},
        "policy": {"target_versions": {runtime: dict(families) for runtime, families in TARGET_VERSIONS.items()}, "enabled_targets": sorted(_TARGET_NAMES), "allow_implicit_version_substitution": False, "require_verified_runtime_mapping": True, "frontier_auto_opt_in": False, "min_confidence_for_auto": 0.75},
        "observability": {"log_decisions": True, "record_raw_prompt": False, "private_state_permissions": True},
    }


def parse_config(text: str, *, source: str = "global") -> dict[str, Any]:
    """Parse and validate one JSON layer, returning a fresh plain mapping.

    ``source`` is ``global`` or ``project``. It is intentionally a keyword so
    project consent can be rejected as an attempt to grant transmission.
    """
    if source not in {"global", "project"}:
        raise ConfigError("invalid config source")
    validated = _validate(_parse_json(text))
    if source == "project" and any(validated.get("consent", {}).values()):
        # Consent is authority, not an ordinary precedence setting. A project
        # may revoke it, but cannot grant provider transmission.
        raise ConfigError("project config cannot grant external consent")
    return validated


def merge_config_layers(global_config: Mapping[str, Any], project_config: Mapping[str, Any]) -> RouterConfig:
    """Deep-merge validated global and project layers into an immutable config."""
    if not isinstance(global_config, Mapping) or not isinstance(project_config, Mapping):
        raise ConfigError("config layers must be objects")
    g = _validate(dict(global_config))
    p = _validate(dict(project_config))
    if any(p.get("consent", {}).values()):
        raise ConfigError("project config cannot grant external consent")
    merged = _deep_merge(_default_dict(), g)
    _enforce_project_restrictions(merged, p)
    merged = _deep_merge(merged, p)
    return _freeze_config(merged)


def load_config(global_path: Optional[Union[str, Path]] = None, project_path: Optional[Union[str, Path]] = None,
                *, project_paths=None) -> RouterConfig:
    """Load optional global/project JSON files; project settings deep-override.

    Missing files are equivalent to empty layers. Any malformed present file
    raises a sanitized ``ConfigError`` so the adapter can preserve native args.
    No key value is read; callers obtain ``TYPESAFE_API_KEY`` only at the point
    an independently consented provider request is actually made.
    """
    def read(path: Optional[Union[str, Path]], source: str) -> dict[str, Any]:
        if path is None:
            return {}
        try:
            flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise ConfigError("configuration must be a regular file")
                if source == "global" and os.name == "posix" and (
                        info.st_uid != os.getuid() or info.st_mode & 0o022):
                    raise ConfigError("global config must be owned by current user and not writable by others")
                raw = stream.read(MAX_CONFIG_BYTES + 1)
            if len(raw) > MAX_CONFIG_BYTES:
                raise ConfigError("configuration exceeds size limit")
            text = raw.decode("utf-8")
        except FileNotFoundError:
            return {}
        except (OSError, UnicodeError):
            raise ConfigError(f"could not read {source} config") from None
        return parse_config(text, source=source)

    if project_paths is None:
        return merge_config_layers(read(global_path, "global"), read(project_path, "project"))
    if project_path is not None:
        raise ConfigError("choose one project config scope")
    # Global installations must honor repository-level revocations even when
    # launched in a subdirectory. Each ancestor may only narrow its predecessor.
    merged = _deep_merge(_default_dict(), read(global_path, "global"))
    for path in project_paths:
        layer = read(path, "project")
        _enforce_project_restrictions(merged, layer)
        merged = _deep_merge(merged, layer)
    return _freeze_config(merged)

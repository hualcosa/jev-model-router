"""Bounded private audit records. Never a source of routing authority.

Arguments, recommendations and host reports are distinct. No transcript parsing,
implicit tool/agent join, raw text, provider prose, or unbounded label passthrough.
"""
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
import re
import secrets
import time

from .contracts import ProviderResult
from .state import PrivateStateStore, StateError, _scope_hash, _unique

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_MODEL = re.compile(r"(?:gpt-[0-9]{1,2}(?:\.[0-9]{1,2})?-(?:luna|terra|sol|astra)|claude-(?:haiku|sonnet|opus|fable)-[0-9]{1,2}(?:[.-][0-9]{1,2}){0,2}|haiku|sonnet|opus|fable|fixture-(?:luna|terra|sol|astra|haiku|sonnet|opus|fable))\Z")
_EFFORTS = {"low", "medium", "high", "xhigh", "max", "ultra"}
_SOURCES = {"assessment", "SessionStart", "UserPromptSubmit", "PostModelSwitch", "PostToolUse", "SubagentStart", "SubagentStop", "boundary", "spawn", "root_warning", "preparation"}
_REASONS = set("""active_effort_unknown active_route_unknown boundary_unknown capability_gap capability_unavailable catalog_unavailable classified classifier_abstained classifier_unavailable disabled effort_advisory_only empty_task explicit_override frontier_opt_in_required generic_profiles_disabled invalid_task_envelope invalid_text_encoding low_confidence no_consent_or_payload no_material_gain no_supported_route preflight_disabled preflight_recommendation provider_failure risk_unavailable shadow_mode task_binding_unknown task_too_large unsupported_host_version warnings_disabled worker_routing_disabled unclassified_reason""".split())
_REASONS.update("""scope_changed session_start resume compaction session_end clock_regressed duplicate_event child_task_not_root tool_activity stop_not_completion trusted_task_completed untrusted_or_unmatched_completion untrusted_task_created same_native_task trusted_task_created explicit_preflight linked_same_task clear_acknowledgement explicit_followup explicit_new_task_marker explicit_topic_shift ttl_expired ambiguous_prompt standalone_initial_objective objective_change_not_proven missing_event_identity invalid_tool_name invalid_tool_arguments missing_host_identity missing_or_nontext_task missing_project_or_session missing_tool_use_id tracker_full tracker_unavailable unknown_agent_type unknown_argument_schema unknown_event_schema unrelated_tool unsupported_argument_type unsupported_argument_type_or_copy_limit explicit_pin duplicate_tool_use custom_or_unknown_profile plaintext_unavailable_requires_local_preparation eligible_native_child rewrite_evidence_unavailable invalid_reference cached_decision_unavailable snapshot_changed catalog_changed policy_changed rewrite_emitted warning_emitted already_prepared preparation_issued unavailable""".split())
_PHASES = {
    "boundary": {"new_task", "continuation", "unknown"},
    "spawn": {"not_applicable", "abstain", "eligible", "prepared_task_required", "duplicate", "pinned", "custom_profile", "computed", "cached", "inflight", "error", "unchanged", "emitted"},
    "root_warning": {"emitted"},
    "preparation": {"computed", "cached", "inflight", "error", "issued"},
}
_COMMON = {"schema", "row_id", "timestamp", "runtime", "surface", "host_version", "mode", "source", "scope_hash", "task_hash", "tool_hash", "agent_hash", "data"}
_OBS = {"argument_model", "argument_effort", "actual_model", "actual_effort", "actual_execution", "correlation"}
_ASSESS = {"event", "disposition", "reason", "selected_model", "selected_effort", "recommended_model", "recommended_effort", "confidence", "policy_hash", "snapshot_hash", "catalog_hash", "provider_calls", "provider_status", "elapsed_ms", "requirements"}
_REQ = {"complexity", "reasoning", "tool_complexity", "confidence", "ambiguity", "tier", "risk"}


class TelemetryError(ValueError):
    def __init__(self):
        super().__init__("telemetry_unavailable")


def _dump(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _score(value, maximum=1):
    return type(value) in (int, float) and 0 <= value <= maximum and math.isfinite(value)


def _model(value):
    return value if isinstance(value, str) and _MODEL.fullmatch(value) else None


def _effort(value):
    return value if isinstance(value, str) and value in _EFFORTS else None


def _identifier(scope_hash, value):
    if value is None:
        return None
    if not isinstance(value, str) or not 0 < len(value) <= 256:
        raise TelemetryError()
    return hashlib.sha256((scope_hash + ":" + value).encode("utf-8")).hexdigest()


def _validate(obj):
    if not isinstance(obj, dict) or set(obj) != _COMMON:
        raise TelemetryError()
    if (type(obj["schema"]) is not int or obj["schema"] != 1
            or not isinstance(obj["row_id"], str) or not re.fullmatch(r"[0-9a-f]{32}", obj["row_id"])
            or not _score(obj["timestamp"], 2**53)
            or obj["runtime"] not in ("codex", "claude") or obj["surface"] != "cli"
            or not isinstance(obj["host_version"], str) or not re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{1,3}){2}", obj["host_version"])
            or obj["mode"] not in ("shadow", "warn", "auto_workers")
            or obj["source"] not in _SOURCES):
        raise TelemetryError()
    for key in ("scope_hash", "task_hash", "tool_hash", "agent_hash"):
        v = obj[key]
        if v is None and key != "scope_hash":
            continue
        if not isinstance(v, str) or not _HASH.fullmatch(v):
            raise TelemetryError()
    d = obj["data"]
    if not isinstance(d, dict):
        raise TelemetryError()
    if obj["source"] == "assessment":
        if set(d) - {"policy_provenance"} != _ASSESS or obj["agent_hash"] is not None:
            raise TelemetryError()
        if (d["event"] not in ("root_prompt", "subagent_spawn", "preflight", "prepared_task")
                or d["disposition"] not in ("skip", "defer", "warn_root", "route_worker")
                or d["reason"] not in _REASONS
                or type(d["provider_calls"]) is not int or d["provider_calls"] not in (0, 1)
                or d["provider_status"] not in ("not_called", "success", "failure", "unavailable")
                or (d["provider_calls"] == 0) != (d["provider_status"] == "not_called")
                or not _score(d["elapsed_ms"], 86400000)
                or (d["confidence"] is not None and not _score(d["confidence"]))):
            raise TelemetryError()
        for key in ("selected_model", "recommended_model"):
            if d[key] is not None and _model(d[key]) != d[key]:
                raise TelemetryError()
        for key in ("selected_effort", "recommended_effort"):
            if d[key] is not None and _effort(d[key]) != d[key]:
                raise TelemetryError()
        for key in ("policy_hash", "snapshot_hash", "catalog_hash"):
            if not isinstance(d[key], str) or not _HASH.fullmatch(d[key]):
                raise TelemetryError()
        if d.get("policy_provenance", "unknown") not in ("policy_prior", "unknown"):
            raise TelemetryError()
        req = d["requirements"]
        if req is not None:
            if (not isinstance(req, dict) or set(req) != _REQ or d["provider_status"] != "success"
                    or req["tier"] not in ("T0", "T1", "T2", "T3", "abstain")
                    or req["risk"] not in (None, "low", "medium", "high")):
                raise TelemetryError()
            for k in ("complexity", "reasoning", "tool_complexity", "confidence", "ambiguity"):
                if req[k] is None and k == "ambiguity":
                    continue
                if not _score(req[k]):
                    raise TelemetryError()
    elif obj["source"] in _PHASES:
        if (set(d) != {"phase", "reason"} or d["phase"] not in _PHASES[obj["source"]]
                or d["reason"] not in _REASONS or obj["agent_hash"] is not None):
            raise TelemetryError()
    else:
        if (set(d) != _OBS or d["correlation"] != "unverified" or obj["task_hash"] is not None
                or (obj["runtime"], obj["host_version"]) not in (("codex", "0.163.0"), ("claude", "2.1.303"))):
            raise TelemetryError()
        for key in ("argument_model", "actual_model"):
            if d[key] is not None and _model(d[key]) != d[key]:
                raise TelemetryError()
        for key in ("argument_effort", "actual_effort"):
            if d[key] is not None and _effort(d[key]) != d[key]:
                raise TelemetryError()
        actual = d["actual_model"] is not None or d["actual_effort"] is not None
        if d["actual_execution"] != ("reported_by_host" if actual else "unverified"):
            raise TelemetryError()
        if obj["source"] == "PostToolUse":
            if actual or obj["tool_hash"] is None:
                raise TelemetryError()
        elif d["argument_model"] is not None or d["argument_effort"] is not None:
            raise TelemetryError()
        if obj["source"] in ("SubagentStart", "SubagentStop"):
            if obj["agent_hash"] is None or obj["tool_hash"] is not None:
                raise TelemetryError()
            if obj["runtime"] == "codex" and d["actual_effort"] is not None:
                raise TelemetryError()
            if obj["runtime"] == "claude" and (d["actual_model"] is not None or
                    (obj["source"] == "SubagentStart" and d["actual_effort"] is not None)):
                raise TelemetryError()
        elif obj["agent_hash"] is not None:
            raise TelemetryError()
        if obj["source"] not in ("PostToolUse",) and obj["tool_hash"] is not None:
            raise TelemetryError()
        if d["actual_effort"] == "ultra":
            raise TelemetryError()
        if obj["source"] == "PostModelSwitch" and obj["runtime"] != "claude":
            raise TelemetryError()
        if obj["source"] == "UserPromptSubmit" and obj["runtime"] != "codex":
            raise TelemetryError()
        if obj["source"] != "SubagentStop" and d["actual_effort"] is not None:
            raise TelemetryError()
    return obj


@dataclass(frozen=True)
class TelemetryRecord:
    encoded: str = field(repr=False)

    def __post_init__(self):
        try:
            if not isinstance(self.encoded, str) or len(self.encoded) > 8192:
                raise TelemetryError()
            obj = json.loads(self.encoded, object_pairs_hook=_unique)
            _validate(obj)
            object.__setattr__(self, "encoded", _dump(obj))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError, StateError):
            raise TelemetryError() from None

    def to_dict(self):
        return json.loads(self.encoded)


def _record(profile, mode, scope, source, data, *, task_id=None, tool_id=None, agent_id=None):
    if scope.runtime != profile.runtime.value:
        raise TelemetryError()
    scope_hash = _scope_hash(scope)
    return TelemetryRecord(_dump(dict(schema=1, row_id=secrets.token_hex(16), timestamp=time.time(),
        runtime=profile.runtime.value, surface=profile.surface, host_version=profile.host_version,
        mode=mode, source=source, scope_hash=scope_hash, task_hash=_identifier(scope_hash, task_id),
        tool_hash=_identifier(scope_hash, tool_id), agent_hash=_identifier(scope_hash, agent_id), data=data)))


def observation_record(profile, mode, scope, event):
    """Exact measured CLI schemas only; null means unknown, never inheritance.

    Lifecycle IDs cannot be joined to parent tool calls with documented fields.
    Never inspect tool_response or transcript paths to manufacture that join.
    """
    runtime = profile.runtime.value
    if profile.surface != "cli" or (runtime, profile.host_version) not in (("codex", "0.163.0"), ("claude", "2.1.303")):
        return None
    source = event.get("hook_event_name")
    if source not in _SOURCES - {"assessment", *_PHASES}:
        return None
    agent = event.get("agent_id")
    model = effort = arg_model = arg_effort = tool = None
    if source in ("SubagentStart", "SubagentStop"):
        if not isinstance(agent, str) or not agent:
            return None
        if runtime == "codex":
            model = _model(event.get("model"))
        elif source == "SubagentStop":
            e = event.get("effort")
            effort = _effort(e.get("level")) if isinstance(e, dict) else None
            if effort == "ultra":
                effort = None
    else:
        if agent is not None:
            return None
        if source == "PostToolUse":
            if event.get("tool_name") not in profile.tools:
                return None
            args = event.get("tool_input")
            tool = event.get("tool_use_id")
            if not isinstance(args, dict) or not isinstance(tool, str) or not tool:
                return None
            arg_model = _model(args.get("model"))
            arg_effort = _effort(args.get("reasoning_effort" if runtime == "codex" else "effort"))
        elif source == "PostModelSwitch":
            if runtime != "claude":
                return None
            model = _model(event.get("to_model"))
        elif source == "UserPromptSubmit":
            if runtime != "codex":
                return None
            model = _model(event.get("model"))
        else:
            model = _model(event.get("model"))
    data = dict(argument_model=arg_model, argument_effort=arg_effort, actual_model=model,
                actual_effort=effort, actual_execution="reported_by_host" if model or effort else "unverified",
                correlation="unverified")
    return _record(profile, mode, scope, source, data, tool_id=tool, agent_id=agent)


def assessment_record(profile, mode, scope, envelope, decision, snapshot, provider, calls, elapsed_ms):
    req = provider.requirements if isinstance(provider, ProviderResult) else None
    requirements = None if req is None else {k: v for k, v in req.to_dict().items() if k in _REQ}
    data = dict(event=envelope.event.value, disposition=decision.disposition.value,
        reason=decision.reason_code if decision.reason_code in _REASONS else "unclassified_reason",
        selected_model=_model(decision.selected_model), selected_effort=_effort(decision.selected_effort),
        recommended_model=_model(decision.recommended_model), recommended_effort=_effort(decision.recommended_effort),
        confidence=decision.confidence,
        policy_provenance=decision.provenance if decision.provenance == "policy_prior" else "unknown",
        policy_hash=hashlib.sha256(decision.version.encode("utf-8")).hexdigest(),
        snapshot_hash=snapshot.snapshot_id, catalog_hash=snapshot.catalog_id, provider_calls=calls,
        provider_status="not_called" if not calls else provider.status.value if isinstance(provider, ProviderResult) else "failure",
        elapsed_ms=elapsed_ms, requirements=requirements)
    return _record(profile, mode, scope, "assessment", data, task_id=envelope.task_id, tool_id=envelope.tool_call_id)


def activity_record(profile, mode, scope, source, phase, reason, *, task_id=None, tool_id=None):
    return _record(profile, mode, scope, source,
        {"phase": phase, "reason": reason if reason in _REASONS else "unclassified_reason"},
        task_id=task_id, tool_id=tool_id)


class TelemetryLog:
    """Three bounded atomic JSONL files, serialized by existing private state.lock.

    A crash during rotation can duplicate old rows; read deduplicates row_id.
    It cannot retry classification, repair unsafe paths, or change routing state.
    Construction performs no I/O. read never creates root/lock or cleans files.
    """
    NAMES = ("telemetry.jsonl", "telemetry.1.jsonl", "telemetry.2.jsonl")

    def __init__(self, store, *, max_bytes=262144):
        if not isinstance(store, PrivateStateStore) or type(max_bytes) is not int or not 8192 <= max_bytes <= 1048576:
            raise TelemetryError()
        self.store, self.max_bytes = store, max_bytes

    def _read_file(self, rootfd, name):
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=rootfd)
        except FileNotFoundError:
            return b"", []
        try:
            if self.store._check_file(fd).st_size > self.max_bytes:
                raise TelemetryError()
            raw = b""
            while len(raw) <= self.max_bytes:
                part = os.read(fd, min(65536, self.max_bytes + 1 - len(raw)))
                if not part:
                    break
                raw += part
            if len(raw) > self.max_bytes or (raw and not raw.endswith(b"\n")):
                raise TelemetryError()
            rows = [TelemetryRecord(line.decode("ascii")) for line in raw.splitlines()]
            return raw, rows
        finally:
            os.close(fd)

    def _publish(self, rootfd, name, raw):
        # Shared temp namespace: interrupted writes are safely cleaned by the
        # next state transaction, under the same lock and private-file checks.
        temporary = ".tmp-" + secrets.token_hex(16)
        fd = None
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=rootfd)
            self.store._check_file(fd)
            view = memoryview(raw)
            while view:
                n = os.write(fd, view)
                if not n:
                    raise TelemetryError()
                view = view[n:]
            os.fsync(fd)
            os.close(fd)
            fd = None
            os.replace(temporary, name, src_dir_fd=rootfd, dst_dir_fd=rootfd)
            os.fsync(rootfd)
        finally:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(temporary, dir_fd=rootfd)
            except FileNotFoundError:
                pass

    def append(self, record):
        try:
            if not isinstance(record, TelemetryRecord):
                raise TelemetryError()
            row = (record.encoded + "\n").encode("ascii")
            if len(row) > self.max_bytes:
                raise TelemetryError()
            with self.store._transaction() as (rootfd, _data, _now):
                existing = [self._read_file(rootfd, name)[0] for name in self.NAMES]
                if len(existing[0]) + len(row) > self.max_bytes:
                    self._publish(rootfd, self.NAMES[2], existing[1])
                    self._publish(rootfd, self.NAMES[1], existing[0])
                    existing[0] = b""
                self._publish(rootfd, self.NAMES[0], existing[0] + row)
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError, OverflowError, StateError):
            raise TelemetryError() from None

    def read(self):
        try:
            with self.store._read_lock() as rootfd:
                if rootfd is None:
                    return []
                rows, seen = [], {}
                for name in reversed(self.NAMES):
                    for record in self._read_file(rootfd, name)[1]:
                        row_id = record.to_dict()["row_id"]
                        if row_id in seen:
                            if seen[row_id] != record.encoded:
                                raise TelemetryError()
                        else:
                            rows.append(record)
                            seen[row_id] = record.encoded
                return rows
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError, OverflowError, StateError):
            raise TelemetryError() from None

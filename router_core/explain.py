"""Explain retained evidence offline; never a routing or execution authority."""
import hashlib
import json
import os
import re

from .state import PrivateStateStore, StateScope, StateError, _scope_hash
from .telemetry import TelemetryLog, TelemetryError, _model, _effort

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ROW = re.compile(r"[0-9a-f]{32}\Z")
_VERSION = re.compile(r"[0-9]{1,3}(?:\.[0-9]{1,3}){0,2}\Z")
_SOURCES = {"p0_cli_spike_2026-10-19", "official_app_server_model_list", "claude_sonnet_alias_native_2026-10-19"}
_FAMILIES = {"haiku", "sonnet", "opus", "fable", "luna", "terra", "sol", "astra"}
_TOOLS = {"Agent", "Task", "spawn_agent", "collaboration.spawn_agent", "collaborationspawn_agent"}
_REASONS = {
    "classified": "Policy selected a worker route from the assessment and saved catalog. Selection is not execution proof.",
    "shadow_mode": "Shadow mode recorded a recommendation without routing arguments or a root warning.",
    "capability_gap": "Policy found a capability gap relative to the observed root. This is a policy prior, not measured task quality.",
    "active_route_unknown": "Current root identity did not match a unique verified catalog route; root advice was deferred.",
    "active_effort_unknown": "Current root effort was insufficiently known for same-model effort advice.",
    "no_material_gain": "Policy found no material gain relative to the observed root route.",
    "no_consent_or_payload": "Assessment could not proceed under the recorded consent or minimized-payload constraints.",
    "classifier_unavailable": "No usable classifier result was available; native execution was left unchanged.",
    "low_confidence": "Classifier confidence did not meet the configured routing threshold.",
    "explicit_pin": "An explicit model or effort pin prevented router selection.",
    "explicit_override": "An explicit pin or custom/unknown profile prevented router selection.",
    "custom_or_unknown_profile": "Custom or unrecognized agent profiles retain native behavior.",
    "rewrite_evidence_unavailable": "Verified hook-conflict or permission-mode evidence was insufficient for rewriting.",
    "rewrite_emitted": "Router emitted updatedInput; this alone does not prove the host applied it or executed that route.",
    "warning_emitted": "Router emitted a nonblocking warning; this alone does not prove visible presentation.",
    "boundary_unknown": "The logical task boundary was not established; root assessment was deferred.",
    "missing_event_identity": "Native event identity was missing; the boundary was not treated as a new root task.",
    "already_prepared": "A cached assessment cannot mint another single-use prepared capability.",
    "snapshot_changed": "Saved and current policy/catalog snapshots differed; no rewrite was applied.",
    "effort_advisory_only": "An adequate supported effort was unavailable; no worker route was applied.",
}


class ExplainError(ValueError):
    def __init__(self, code="explain_unavailable"):
        self.code = code if code in {"explain_unavailable", "invalid_explain_selection"} else "explain_unavailable"
        super().__init__(self.code)


def scope_hash_for(runtime, project, session_id):
    """Explicit CLI selection only; no environment/config/session guessing."""
    try:
        if runtime not in ("claude", "codex") or not isinstance(session_id, str) or not 0 < len(session_id) <= 256:
            raise ExplainError("invalid_explain_selection")
        return _scope_hash(StateScope(runtime, os.path.realpath(os.fspath(project)), session_id))
    except (OSError, ValueError, TypeError, UnicodeError, StateError):
        raise ExplainError("invalid_explain_selection") from None


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mapping(entry):
    """Never dump free-form catalog evidence, labels, paths or config content."""
    provenance = entry["mapping_provenance"]
    version = entry["target_version"]
    return {"family": entry["family"] if entry["family"] in _FAMILIES else None,
        "target_version": version if _VERSION.fullmatch(version) else None,
        "runtime_model_id": _model(entry["runtime_model_id"]),
        "tool_name": entry["tool_name"] if entry["tool_name"] in _TOOLS else None,
        "supported_efforts": [e for e in entry["supported_efforts"] if _effort(e)],
        "mapping_status": entry["mapping_status"], "availability_source": entry["availability_source"],
        "mapping_provenance": provenance if provenance in _SOURCES else "unrecognized_source",
        "mapping_provenance_hash": _digest(provenance),
        "mapping_evidence_hash": entry["mapping_evidence_sha256"],
        "root_model_ids": [v for v in entry.get("root_model_ids", []) if _model(v)]}


def _metadata(row, snapshot, unavailable):
    d = row["data"]
    result = {"status": "unavailable" if unavailable else "missing_or_expired",
              "snapshot_hash": d["snapshot_hash"], "catalog_hash": d["catalog_hash"],
              "live_checked": False, "matched_mappings": []}
    if snapshot is None:
        return result
    if (snapshot.snapshot_id != d["snapshot_hash"] or snapshot.catalog_id != d["catalog_hash"]
            or _digest(snapshot.policy_version) != d["policy_hash"]):
        result["status"] = "hash_mismatch"
        return result
    result.update(status="recorded_snapshot", policy_version=snapshot.policy_version
                  if _VERSION.fullmatch(snapshot.policy_version) else None)
    controls = json.loads(snapshot.config_json)
    policy = controls["policy"]
    result["recorded_policy_controls"] = {
        "mode": controls["mode"], "min_confidence_for_auto": policy["min_confidence_for_auto"],
        "frontier_auto_opt_in": policy["frontier_auto_opt_in"],
        "require_verified_runtime_mapping": policy["require_verified_runtime_mapping"],
        "enabled_targets": sorted(policy["enabled_targets"]),
        "target_versions": {runtime: {family: version if _VERSION.fullmatch(version) else None
                                     for family, version in versions.items() if family in _FAMILIES}
                            for runtime, versions in policy["target_versions"].items() if runtime in ("claude", "codex")}}
    route = d["selected_model"] or d["recommended_model"]
    if route is not None:
        entries = json.loads(snapshot.catalog_json)["entries"]
        matches = [e for e in entries if (e["runtime"], e["surface"], e["host_version"]) ==
                   (row["runtime"], row["surface"], row["host_version"]) and
                   (e["runtime_model_id"] == route or
                    (d["event"] == "root_prompt" and route in e.get("root_model_ids", [])))]
        result["matched_mappings"] = [_mapping(e) for e in matches]
    # More than one tool mapping is not evidence which native tool was selected.
    result["mapping_identity"] = "unique" if len(result["matched_mappings"]) == 1 else "ambiguous" if result["matched_mappings"] else "not_resolved"
    return result


def _description(row):
    source, data = row["source"], row["data"]
    if "reason" in data:
        return _REASONS.get(data["reason"], "Recorded outcome: " + data["reason"].replace("_", " ") + ".")
    if source == "PostToolUse":
        return "Post-tool model and effort are arguments, not actual execution evidence."
    if source in ("SubagentStart", "SubagentStop"):
        return "Available child fields are independent host reports. Lifecycle IDs do not establish a parent-tool join."
    return "Available root fields are host reports at this event, not a live runtime check."


def explain_history(store, scope_hash, *, runtime=None, surface="cli", row_id=None, limit=20):
    """Bounded retained timeline, explicitly scoped and never reclassified.

    Reads telemetry and immutable snapshots independently under shared locks.
    Content hashes, not temporal adjacency, bind metadata to assessments. No
    task/argument/child execution join or provider totals are inferred.
    """
    if (not isinstance(store, PrivateStateStore) or not isinstance(scope_hash, str) or not _HASH.fullmatch(scope_hash)
            or runtime not in (None, "claude", "codex") or surface not in ("cli", "desktop")
            or (row_id is not None and (not isinstance(row_id, str) or not _ROW.fullmatch(row_id)))
            or type(limit) is not int or not 1 <= limit <= 50):
        raise ExplainError("invalid_explain_selection")
    try:
        rows = [r.to_dict() for r in TelemetryLog(store).read()]
        scoped = [r for r in rows if r["scope_hash"] == scope_hash and r["surface"] == surface
                  and (runtime is None or r["runtime"] == runtime)]
        selected = [r for r in scoped if r["row_id"] == row_id] if row_id is not None else scoped[-limit:]
        refs = {r["data"]["snapshot_hash"] for r in selected if r["source"] == "assessment"}
        unavailable = False
        try:
            snapshots = store.read_snapshots(scope_hash, refs)
        except StateError:
            snapshots, unavailable = {}, True
        explained = []
        for row in selected:
            item = {"record": row, "explanation": _description(row)}
            if row["source"] == "assessment":
                d = row["data"]
                item["policy_provenance"] = d.get("policy_provenance", "unknown_not_recorded")
                item["catalog"] = _metadata(row, snapshots.get(d["snapshot_hash"]), unavailable)
            explained.append(item)
        return {"schema":1, "status":"explained" if selected else "no_records", "scope_hash":scope_hash,
                "retained_scope_records":len(scoped), "returned_records":len(explained), "records":explained,
                "external_calls":0, "state_modified":False, "current_runtime_checked":False,
                "history":"bounded_rotating_best_effort_not_complete_or_exactly_once",
                "order":"persisted_record_order_not_a_cross_process_causal_join",
                "execution_correlation":"unverified_no_parent_tool_to_child_join",
                "notice":"Recorded snapshots are historical, not current availability/entitlement checks. Missing history does not prove disabled routing, zero calls, success or savings."}
    except ExplainError:
        raise
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError, OverflowError, StateError, TelemetryError):
        raise ExplainError() from None

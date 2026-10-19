"""Thin native event adapters. No inference proxy or private transcript reader.

Capabilities are injected by trusted installation/diagnostic code, never hook
arguments or project config. Unknown host/surface/conflicts/permission semantics
abstain. Only native agent-spawn route fields can be changed.
"""
from dataclasses import dataclass
import hashlib
import json
import os
import re
import time

from .boundary import BoundaryClass, BoundaryEvent, BoundaryScope, Lifecycle
from .catalog import CatalogRegistry, CapabilityRecord
from .contracts import EventKind, RouteDisposition, Runtime, TaskEnvelope
from .policy import POLICY_VERSION, PolicyScope, assess
from .snapshots import VersionSnapshot
from .privacy import DEFAULT_SYNTHETIC_TASKS
from .advisory import root_warning
from .telemetry import TelemetryLog, assessment_record, observation_record, activity_record
from .spawn import (AssessmentTracker, CapabilityProfile, SpawnStatus, SpawnToolSchema,
                    assess_child_spawn)


@dataclass(frozen=True)
class NativeProfile:
    spawn: CapabilityProfile
    catalog: CatalogRegistry
    # Even exact model support is not proof that allow preserves permissions.
    safe_rewrite_permission_modes: frozenset = frozenset()
    conflicts_checked: bool = False

    def __post_init__(self):
        modes = {"default", "plan", "acceptEdits", "auto", "dontAsk", "bypassPermissions"}
        if (not isinstance(self.spawn, CapabilityProfile) or not isinstance(self.catalog, CatalogRegistry)
                or type(self.conflicts_checked) is not bool
                or not isinstance(self.safe_rewrite_permission_modes, frozenset)
                or not self.safe_rewrite_permission_modes.issubset(modes)):
            raise ValueError("invalid_native_profile")


def bootstrap_profile(runtime, surface, version):
    """Only previously measured CLI primitives; not a complete model catalog.

    No desktop extrapolation or unmeasured Opus/Fable/Terra/Astra mappings. A
    diagnostic must supply conflict/permission evidence before auto mutation.
    Claude Haiku/Sonnet Medium mappings have isolated native execution proof.
    """
    runtime = Runtime(runtime)
    if surface != "cli":
        return None
    if runtime is Runtime.CLAUDE and version == "2.1.303":
        tool, task, type_field, generic, effort = "Agent", "prompt", "subagent_type", "general-purpose", "effort"
        model, family, generation = "haiku", "haiku", "5.5"
        fields = {"prompt": {"string"}, "description": {"string"}, "subagent_type": {"string"},
                  "model": {"string", "null"}, "effort": {"string", "null"},
                  "run_in_background": {"boolean"}}
    elif runtime is Runtime.CODEX and version == "0.163.0":
        tool, task, type_field, generic, effort = "collaborationspawn_agent", "message", "agent_type", "default", "reasoning_effort"
        model, family, generation = "gpt-6-luna", "luna", "6"
        fields = {"message": {"string"}, "task_name": {"string"}, "agent_type": {"string"},
                  "model": {"string", "null"}, "reasoning_effort": {"string", "null"},
                  "fork_turns": {"string"}, "description": {"string"}}
    else:
        return None
    schema = SpawnToolSchema(frozenset(fields), task, {k: frozenset(v) for k, v in fields.items()},
                             agent_type_field=type_field, generic_agent_types=frozenset({generic}),
                             plaintext_task=runtime is Runtime.CLAUDE)
    spawn = CapabilityProfile(runtime, surface, version, "native-v1", {tool: schema})
    catalog = CatalogRegistry((CapabilityRecord(runtime, surface, version, family, generation, model,
        tool, "model", effort, ("medium",), "verified", "Native P0 model/effort execution proof",
        "p0_cli_spike_2026-10-19", "2026-10-19T14:19:10Z", "user_assumption",
        root_model_ids=("claude-haiku-5-5",) if runtime is Runtime.CLAUDE else ()),))
    if runtime is Runtime.CLAUDE:
        catalog = CatalogRegistry(catalog.records + (CapabilityRecord(runtime, surface, version,
            "sonnet", "5.5", "sonnet", tool, "model", effort, ("medium",), "verified",
            "Isolated Opus/High parent, exact generic Agent.model=sonnet/effort=medium; native result.modelUsage Sonnet5.5 plus childStop Medium",
            "claude_sonnet_alias_native_2026-10-19", "2026-10-19T21:04:15Z", "user_assumption",
            root_model_ids=("claude-sonnet-5-5",)),))
    return NativeProfile(spawn, catalog)


def _text(value, limit=256):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def _hash(*values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode("ascii")).hexdigest()


class NativeAdapter:
    def __init__(self, profile, config, store, classify, *, project_id, clock=time.monotonic,
                 synthetic_tasks=DEFAULT_SYNTHETIC_TASKS):
        self.profile, self.config, self.store, self.classify = profile, config, store, classify
        self.project_id, self.clock = os.path.realpath(project_id), clock
        # Trusted shipped fixtures only; never sourced from project/tool input.
        self.synthetic_tasks = synthetic_tasks
        # No I/O at construction; disabled/logging-off means no telemetry calls.
        self.telemetry = TelemetryLog(store)

    def _log(self, factory):
        if self.config.mode == "disabled" or not self.config.observability.log_decisions:
            return
        try:
            record = factory()
            if record is not None:
                self.telemetry.append(record)
        except Exception:
            # Audit failure must never change native output, call count or policy.
            pass

    def _activity(self, scope, source, phase, reason, *, task_id=None, tool_id=None):
        self._log(lambda: activity_record(self.profile.spawn, self.config.mode, scope,
            source, phase, reason, task_id=task_id, tool_id=tool_id))

    def assess(self, envelope, scope, *, boundary_is_new=False, tool_name=None):
        """Keep metadata durable before any new external assessment."""
        snapshot = VersionSnapshot.capture(POLICY_VERSION, self.config, self.profile.catalog)
        self.store.put_snapshot(scope, snapshot)
        tool = tool_name or next(iter(self.profile.spawn.tools))
        calls, provider = 0, None
        started = time.monotonic()

        def classify(payload):
            nonlocal calls, provider
            calls += 1
            provider = self.classify(payload)
            return provider

        decision = assess(envelope, classify, self.profile.catalog, self.config,
            PolicyScope(self.profile.spawn.surface, self.profile.spawn.host_version, tool),
            boundary_is_new=boundary_is_new, synthetic_tasks=self.synthetic_tasks)
        self._log(lambda: assessment_record(self.profile.spawn, self.config.mode, scope,
            envelope, decision, snapshot, provider, calls, (time.monotonic() - started) * 1000))
        return decision

    def handle(self, event):
        """Return supported JSON or None. Native run always continues on error."""
        try:
            return self._handle(event)
        except Exception:
            # Never return exception text, task excerpts, credential paths or a
            # blocking decision. Diagnostics are separate sanitized tooling.
            return None

    def _handle(self, event):
        if self.profile is None or self.config.mode == "disabled" or not isinstance(event, dict):
            return None
        session_id = event.get("session_id")
        cwd = event.get("cwd")
        if not _text(session_id) or not isinstance(cwd, str) or os.path.realpath(cwd) != self.project_id:
            return None
        scope = BoundaryScope(self.profile.spawn.runtime.value, self.project_id, session_id)
        name = event.get("hook_event_name")
        self._log(lambda: observation_record(self.profile.spawn, self.config.mode, scope, event))
        # Root advisory metadata must not be overwritten by worker lifecycle or
        # a nested worker's prompt. Such events are not root task boundaries.
        if event.get("agent_id") is not None and name != "PreToolUse":
            return None
        if name == "PreToolUse":
            return self._spawn(event, scope)
        effort = event.get("effort")
        if isinstance(effort, dict):
            effort = effort.get("level")
        effort = effort if effort in ("low", "medium", "high", "xhigh", "max") else None
        if name == "PostModelSwitch" and self.profile.spawn.runtime is Runtime.CLAUDE:
            model = event.get("to_model")
            self.store.observe_root(scope, model=model if _text(model) else None, effort=effort)
            return None
        lifecycle = {"SessionStart": Lifecycle.SESSION_START, "SessionEnd": Lifecycle.SESSION_END,
                     "PostCompact": Lifecycle.COMPACTION, "UserPromptSubmit": Lifecycle.USER_PROMPT,
                     "Stop": Lifecycle.STOP, "TaskCreated": Lifecycle.TASK_CREATED,
                     "TaskCompleted": Lifecycle.TASK_COMPLETED}
        if name not in lifecycle:
            return None
        kind = lifecycle[name]
        if name == "SessionStart" and event.get("source") in ("resume", "compact", "fork"):
            kind = Lifecycle.RESUME if event.get("source") != "compact" else Lifecycle.COMPACTION
        prompt = event.get("prompt", "") if name == "UserPromptSubmit" else ""
        if not isinstance(prompt, str):
            return None
        # Task lifecycle tools can be nested subtasks, not necessarily a new
        # ROOT task. Do not trust them until the host-specific adapter verifies
        # root provenance. Session and user prompt events remain usable.
        turn_id = event.get("turn_id") if self.profile.spawn.runtime is Runtime.CODEX else event.get("prompt_id")
        boundary = BoundaryEvent(scope, kind, self.clock(), event_id=event.get("event_id"),
                                 turn_id=turn_id, prompt=prompt,
                                 trusted_native=False)
        observed_at_boundary = None
        if name == "SessionStart" or (name == "UserPromptSubmit" and self.profile.spawn.runtime is Runtime.CODEX):
            observed_at_boundary = {"model": event.get("model") if _text(event.get("model")) else None,
                                    "effort": effort}
        # Bind transition/reset and host observation atomically. An older
        # callback cannot overwrite a newer prompt's model between transactions.
        transition = self.store.apply_boundary(boundary, root_observation=observed_at_boundary)
        self._activity(scope, "boundary", transition.classification.value, transition.reason,
                       task_id=transition.logical_task_id)
        if (name == "SessionStart" and self.profile.spawn.runtime is Runtime.CODEX
                and self.config.mode == "auto_workers"):
            guidance = ("For generic delegated tasks, call intelligent_router.prepare_task with "
                        f"session_id={json.dumps(session_id)}, a stable task_id per assignment, and original task_text, then use the returned "
                        "task_name in native spawn without model/reasoning_effort. Preserve the task unchanged. "
                        "Skip custom profiles and explicit pins. Do not repeat preparation with a new task_id on retry. "
                        "Missing preparation means native inheritance.")
            return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": guidance}}
        if name != "UserPromptSubmit" or transition.classification is not BoundaryClass.NEW_TASK:
            return None
        observed = self.store.get_root(scope)
        envelope = TaskEnvelope(self.profile.spawn.runtime, EventKind.ROOT_PROMPT, session_id,
            transition.logical_task_id, prompt, False, turn_id=turn_id,
            active_root_model=observed.get("model"), active_root_effort=observed.get("effort"))
        result = self.store.run_once(scope, "root:" + envelope.task_id,
            lambda: self.assess(envelope, scope, boundary_is_new=True))
        decision = result.decision
        if decision is None or decision.disposition is not RouteDisposition.WARN_ROOT:
            return None
        current = VersionSnapshot.capture(POLICY_VERSION, self.config, self.profile.catalog)
        if decision.version != POLICY_VERSION or decision.snapshot_version != current.snapshot_id:
            return None
        # Render before claiming delivery: invalid presentation must not consume
        # the once-per-task receipt or interpolate arbitrary catalog prose.
        message = root_warning(envelope, decision)
        if message is None:
            return None
        fingerprint = _hash(envelope.task_id, decision.recommended_model, decision.recommended_effort, decision.version)
        if not self.store.claim_warning(scope, fingerprint, task_id=envelope.task_id, root_observation=observed):
            return None
        self._activity(scope, "root_warning", "emitted", "warning_emitted", task_id=envelope.task_id)
        return {"systemMessage": message,
                "hookSpecificOutput": {"hookEventName": name, "additionalContext": message}}

    def _spawn(self, event, scope):
        # Ignore unrelated tools completely, including telemetry.
        if event.get("tool_name") not in self.profile.spawn.tools:
            return None
        def log(phase, reason, task_id=None):
            self._activity(scope, "spawn", phase, reason, task_id=task_id,
                           tool_id=event.get("tool_use_id"))
        if self.config.mode == "auto_workers" and (not self.profile.conflicts_checked or
                event.get("permission_mode") not in self.profile.safe_rewrite_permission_modes):
            log("unchanged", "rewrite_evidence_unavailable")
            return None
        profile = self.profile.spawn
        recognized = assess_child_spawn(profile=profile, event_name="PreToolUse",
            event_schema_version=profile.input_schema_version, tool_name=event.get("tool_name"),
            tool_input=event.get("tool_input"), host_version=profile.host_version, surface=profile.surface,
            project_id=self.project_id, session_id=scope.session_id, tool_use_id=event.get("tool_use_id"),
            tracker=AssessmentTracker())
        log(recognized.status.value, recognized.reason_code, recognized.task_id)
        # Preparation cannot know the eventual native agent_type. Recheck the
        # actual validated spawn before consuming a reference or cached claim;
        # otherwise an explicit generic profile bypasses this user restriction.
        if recognized.status in (SpawnStatus.PREPARED_TASK_REQUIRED, SpawnStatus.ELIGIBLE):
            schema = profile.tools[event["tool_name"]]
            if (not self.config.workers.allow_verified_generic_type and schema.agent_type_field
                    and recognized.original_args.get(schema.agent_type_field) is not None):
                log("unchanged", "generic_profiles_disabled", recognized.task_id)
                return None
        if recognized.status is SpawnStatus.PREPARED_TASK_REQUIRED:
            original = recognized.copy_original_args()
            reference = original.get("task_name")
            if not isinstance(reference, str) or re.fullmatch(r"router_[0-9a-f]{32,64}", reference) is None:
                log("unchanged", "invalid_reference", recognized.task_id)
                return None
            # Single-use consumption is inside a persistent run-once claim so
            # duplicate native hooks can replay their cached rewrite safely.
            result = self.store.run_once(scope, recognized.task_id,
                lambda: self.store.consume_prepared(scope, reference))
        elif recognized.status is SpawnStatus.ELIGIBLE:
            result = self.store.run_once(scope, recognized.task_id,
                lambda: self.assess(recognized.envelope, scope, tool_name=event["tool_name"]))
        else:
            return None
        decision = result.decision
        log(result.disposition.value, decision.reason_code if decision else "cached_decision_unavailable", recognized.task_id)
        if decision is None or decision.disposition is not RouteDisposition.ROUTE_WORKER or self.config.mode != "auto_workers":
            return None
        current = VersionSnapshot.capture(POLICY_VERSION, self.config, self.profile.catalog)
        if (decision.version != POLICY_VERSION or decision.snapshot_version != current.snapshot_id
                or decision.catalog_version != current.catalog_id):
            log("unchanged", "snapshot_changed", recognized.task_id)
            return None
        # Revalidate prepared/cached decisions against CURRENT catalog, config
        # and native field support, not merely their earlier classification.
        matching = [r for r in self.profile.catalog.records if r.runtime_model_id == decision.selected_model
                    and r.runtime is profile.runtime and r.surface == profile.surface
                    and r.host_version == profile.host_version and r.tool_name == event["tool_name"]
                    and r.mapping_status == "verified" and r.availability_source != "unknown"
                    and decision.selected_effort in r.supported_efforts]
        if len(matching) != 1:
            log("unchanged", "catalog_changed", recognized.task_id)
            return None
        record = matching[0]
        version = self.config.policy.target_versions.get(profile.runtime.value, {}).get(record.family)
        if ((version is not None and version != record.target_version) or
                f"{profile.runtime.value}.{record.family}" not in self.config.policy.enabled_targets or
                (record.family in ("fable", "astra") and not self.config.policy.frontier_auto_opt_in) or
                decision.confidence is None or decision.confidence < self.config.policy.min_confidence_for_auto):
            log("unchanged", "policy_changed", recognized.task_id)
            return None
        original = recognized.copy_original_args()
        updated = dict(original)
        updated[record.model_field] = decision.selected_model
        if decision.selected_effort is not None:
            updated[record.effort_field] = decision.selected_effort
        output = {"hookEventName": "PreToolUse", "updatedInput": updated}
        if profile.runtime is Runtime.CODEX:
            output["permissionDecision"] = "allow"
        log("emitted", "rewrite_emitted", recognized.task_id)
        return {"hookSpecificOutput": output}

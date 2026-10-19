"""Local Codex plaintext preparation; no inference proxy or task execution."""
import re
from .boundary import BoundaryScope
from .contracts import EventKind, RouteDisposition, TaskBinding, TaskEnvelope


class PreparationService:
    def __init__(self, adapter, *, refresh=None):
        self.adapter = adapter
        self.refresh = refresh

    def prepare(self, *, session_id, task_text, request_id):
        try:
            adapter = self.refresh() if self.refresh is not None else self.adapter
            if adapter is None:
                return {"ok": False, "reason": "disabled_or_unsupported"}
            if not isinstance(request_id, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,80}", request_id) is None:
                return {"ok": False, "reason": "invalid_task_id"}
            profile = adapter.profile
            if profile is None or profile.spawn.runtime.value != "codex" or adapter.config.mode == "disabled":
                return {"ok": False, "reason": "disabled_or_unsupported"}
            if adapter.config.mode == "auto_workers" and not profile.conflicts_checked:
                return {"ok": False, "reason": "rewrite_evidence_unavailable"}
            scope = BoundaryScope("codex", adapter.project_id, session_id)
            # SessionStart context supplies this native ID. Guessing an ID does
            # not register a scope or authorize provider transmission.
            if adapter.store.get_boundary(scope).last_activity is None:
                return {"ok": False, "reason": "session_unregistered"}
            envelope = TaskEnvelope("codex", EventKind.PREPARED_TASK, session_id, "prepare:" + str(request_id),
                task_text, False, task_binding=TaskBinding.ORCHESTRATOR_ATTESTED)
            result = adapter.store.run_once(scope, envelope.task_id,
                lambda: adapter.assess(envelope, scope))
            decision = result.decision
            adapter._activity(scope, "preparation", result.disposition.value,
                decision.reason_code if decision else "unavailable", task_id=envelope.task_id)
            if decision is None or decision.disposition is not RouteDisposition.ROUTE_WORKER:
                return {"ok": False, "reason": decision.reason_code if decision else "unavailable"}
            # A transport/task retry cannot mint fresh capabilities from a
            # cached classification. Crash/lost delivery sacrifices routing,
            # not the at-most-once provider and single-use guarantees.
            if result.disposition.value != "computed":
                return {"ok": False, "reason": "already_prepared"}
            # No plaintext persisted; reference is scoped, expiring and one-use.
            reference = adapter.store.issue_prepared(scope, decision)
            adapter._activity(scope, "preparation", "issued", "preparation_issued", task_id=envelope.task_id)
            return {"ok": True, "task_name": reference, "task_binding": "orchestrator_attested",
                    "instructions": "Delegate original task unchanged with task_name; omit model and reasoning_effort."}
        except Exception:
            return {"ok": False, "reason": "unavailable"}

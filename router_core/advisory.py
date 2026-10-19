"""Bounded root-only advisory presentation; never host mutations or task prose."""
import re

from .contracts import EventKind, RouteDisposition, Runtime

_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}\Z")
_EFFORTS = {"low", "medium", "high", "xhigh", "max"}


def root_warning(envelope, decision):
    """Render only a policy-approved capability gap, not arbitrary provider text.

    Caller must verify current snapshot/catalog and atomically claim delivery.
    None is a no-op, never an approval/blocking response.
    """
    if (envelope.event is not EventKind.ROOT_PROMPT or decision.event is not EventKind.ROOT_PROMPT
            or decision.disposition is not RouteDisposition.WARN_ROOT
            or decision.reason_code != "capability_gap" or decision.confidence is None
            or not all(isinstance(value, str) and _LABEL.fullmatch(value)
                       for value in (envelope.active_root_model, decision.recommended_model))
            or decision.recommended_effort not in _EFFORTS):
        return None
    current_effort = envelope.active_root_effort if envelope.active_root_effort in _EFFORTS else "unknown effort"
    same_model = envelope.active_root_model == decision.recommended_model
    action = "higher effort on the same model" if same_model else "a model change"
    rationale = ("the classified task exceeds the current effort prior" if same_model else
                 "the classified task requires a higher capability tier in the routing prior")
    guidance = ("Use /model manually to choose the model and supported effort" if envelope.runtime is Runtime.CODEX else
                "Use /model for a manual model change; use the host's supported effort control for effort")
    return (f"Router advisory during task submission (nonblocking): consider {action}: "
            f"{decision.recommended_model} / {decision.recommended_effort} "
            f"(current: {envelope.active_root_model} / {current_effort}). "
            f"Reason: {rationale}. Classifier confidence {decision.confidence:.2f}; "
            "this is a policy prior, not a measured quality or savings guarantee. "
            f"Main model/effort unchanged; execution is not paused. {guidance}. "
            "For assessment before a future submission, run explicit router preflight.")

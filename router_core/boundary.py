"""Conservative, in-memory root task boundary state machine (RTE-018).

This module is deliberately independent of runtime adapters, providers, disk
state, and model configuration. Callers decide whether a NEW_TASK result is
eligible for the separately configured classifier; UNKNOWN is always a no-op.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
import re
from typing import Optional, Tuple


MAX_EVENT_HISTORY = 64
MAX_WARNING_FINGERPRINTS = 64
MAX_OBJECTIVE_TERMS = 32
DEFAULT_TTL_SECONDS = 30 * 60
_TOKEN_RE = re.compile(r"[a-zA-ZÀ-ÖØ-öø-ÿ0-9][a-zA-ZÀ-ÖØ-öø-ÿ0-9_-]*")
_ACKS = frozenset({
    "yes", "yep", "yeah", "ok", "okay", "sure", "continue", "go ahead",
    "proceed", "sim", "s", "isso", "certo", "pode", "pode ser", "continua",
    "continue por favor", "sim por favor", "vai", "manda", "beleza", "perfeito",
    "yes go ahead", "sim pode seguir", "sim pode continuar", "pode continuar", "go on",
    "ok continue", "okay continue", "yes continue",
})
_STOP_WORDS = frozenset({
    "a", "as", "o", "os", "um", "uma", "uns", "umas", "de", "da", "do", "das", "dos",
    "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "que", "e", "ou", "ao",
    "this", "that", "these", "those", "the", "a", "an", "and", "or", "of", "to", "for",
    "in", "on", "at", "by", "with", "from", "as", "is", "are", "be", "it", "its", "we",
    "i", "you", "please", "can", "could", "would", "should", "help", "me", "my", "our",
    "e.g", "please", "implement", "create", "build", "fix", "update", "change", "add", "make",
    "analyze", "review", "write", "explain", "meu", "minha", "meus", "minhas", "favor",
    "implemente", "crie", "construa", "corrija", "atualize", "mude", "adicione", "faca", "faça",
    "analise", "revise", "escreva", "explique",
})
_TASK_INTENT_RE = re.compile(
    r"^\s*(?:(?:please|kindly|por favor)\s+)?"
    r"(?:implement|create|build|fix|update|change|add|make|analyze|analyse|review|write|explain|"
    r"design|research|investigate|compare|summarize|draft|plan|test|refactor|remove|replace|"
    r"list|find|search|read|inspect|rename|format|extract|"
    r"implemente|crie|construa|corrija|atualize|mude|adicione|faca|faça|analise|revise|"
    r"escreva|explique|desenhe|pesquise|investigue|compare|resuma|planeje|teste|refatore|remova|substitua|"
    r"liste|procure|busque|encontre|leia|inspecione|renomeie|formate|extraia)\b"
    r"|^\s*(?:can|could|would) you\b|^\s*(?:how|what|why)\b|"
    r"^\s*(?:i need|i want|help me|please help|could we|can we)\b|"
    r"^\s*(?:preciso|quero|pode|poderia|como|por que|o que|ajude|me ajude)\b",
    re.IGNORECASE,
)
_TOPIC_SHIFT_RE = re.compile(
    r"^\s*(?:new task|new objective|different task|different topic|separate request|"
    r"switching gears|unrelated request|another task|another topic|new subject|separately|"
    r"nova tarefa|novo trabalho|novo objetivo|novo assunto|outra tarefa|outro assunto|mudando de assunto|"
    r"agora outra coisa|pedido separado|separadamente)\s*[:,.!—-]?\s*",
    re.IGNORECASE,
)


class BoundaryClass(str, Enum):
    NEW_TASK = "new_task"
    CONTINUATION = "continuation"
    UNKNOWN = "unknown"


class Lifecycle(str, Enum):
    USER_PROMPT = "user_prompt"
    PREFLIGHT = "preflight"
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"
    SUBAGENT_SPAWN = "subagent_spawn"
    TOOL_ACTIVITY = "tool_activity"
    STOP = "stop"
    SESSION_START = "session_start"
    RESUME = "resume"
    COMPACTION = "compaction"
    SESSION_END = "session_end"


class TaskStatus(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    UNCERTAIN = "uncertain"
    COMPLETED = "completed"


@dataclass(frozen=True)
class BoundaryScope:
    """Identity preventing state leakage across runtime/project/session."""

    runtime: str
    project_id: str
    session_id: str

    def __post_init__(self) -> None:
        if self.runtime not in ("claude", "codex"):
            raise ValueError("invalid boundary runtime")
        for name in ("runtime", "project_id", "session_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise ValueError("invalid boundary scope")


@dataclass(frozen=True)
class BoundaryEvent:
    scope: BoundaryScope
    kind: Lifecycle
    timestamp: float
    event_id: Optional[str] = None
    turn_id: Optional[str] = None
    task_id: Optional[str] = None
    linked_task_id: Optional[str] = None
    prompt: str = field(default="", repr=False)
    trusted_native: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.scope, BoundaryScope):
            raise ValueError("invalid boundary scope")
        if not isinstance(self.kind, Lifecycle):
            try:
                object.__setattr__(self, "kind", Lifecycle(self.kind))
            except (ValueError, TypeError):
                raise ValueError("invalid boundary lifecycle") from None
        if isinstance(self.timestamp, bool) or not isinstance(self.timestamp, (int, float)):
            raise ValueError("invalid boundary timestamp")
        try:
            finite_timestamp = math.isfinite(self.timestamp)
        except (OverflowError, TypeError):
            finite_timestamp = False
        if not finite_timestamp or self.timestamp < 0:
            raise ValueError("invalid boundary timestamp")
        for name in ("event_id", "turn_id", "task_id", "linked_task_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value or len(value) > 256):
                raise ValueError("invalid boundary event identifier")
        if not isinstance(self.prompt, str) or len(self.prompt) > 100_000:
            raise ValueError("invalid boundary prompt")
        if not isinstance(self.trusted_native, bool):
            raise ValueError("invalid native boundary evidence")


@dataclass(frozen=True)
class _Receipt:
    key: str
    task_class: BoundaryClass
    reason: str
    logical_task_id: Optional[str]


@dataclass(frozen=True)
class BoundaryState:
    scope: BoundaryScope
    status: TaskStatus = TaskStatus.IDLE
    logical_task_id: Optional[str] = None
    native_task_id: Optional[str] = None
    generation: int = 0
    next_task_number: int = 1
    last_activity: Optional[float] = None
    # Only bounded token hashes are kept, never raw prompt/objective vocabulary.
    objective_terms: Tuple[str, ...] = field(default=(), repr=False)
    receipts: Tuple[_Receipt, ...] = field(default=(), repr=False)
    warned_fingerprints: Tuple[str, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class BoundaryTransition:
    state: BoundaryState
    classification: BoundaryClass
    reason: str
    logical_task_id: Optional[str] = None
    duplicate: bool = False


def initial_state(scope: BoundaryScope) -> BoundaryState:
    return BoundaryState(scope=scope)


def _content_terms(prompt: str) -> Tuple[str, ...]:
    terms = []
    for token in _TOKEN_RE.findall(prompt.casefold()):
        if token not in _STOP_WORDS and len(token) > 1 and token not in terms:
            terms.append(token)
        if len(terms) >= MAX_OBJECTIVE_TERMS:
            break
    return tuple(hashlib.sha256(term.encode("utf-8")).hexdigest()[:32] for term in terms)


def _standalone(prompt: str, terms: Tuple[str, ...]) -> bool:
    # Length alone admits pasted logs/narrative. Require a bounded explicit
    # request/imperative cue plus enough distinct content to be meaningful.
    request_text = _TOPIC_SHIFT_RE.sub("", prompt, count=1)
    request_text = _TOPIC_SHIFT_RE.sub("", request_text, count=1)
    return (_TASK_INTENT_RE.search(request_text) is not None and
            len(_TOKEN_RE.findall(prompt)) >= 8 and len(terms) >= 4)


def _explicit_topic_shift(prompt: str) -> bool:
    return _TOPIC_SHIFT_RE.search(prompt) is not None


def _is_ack(prompt: str) -> bool:
    text = " ".join(_TOKEN_RE.findall(prompt.casefold()))
    if text in _ACKS:
        return True
    words = text.split()
    if len(words) <= 4 and words and words[0] in {
        "yes", "yep", "yeah", "ok", "okay", "sure", "continue", "proceed", "sim", "isso", "certo", "pode", "continua", "vai", "manda",
    }:
        return all(word in {"please", "por", "favor", "thanks", "obrigado", "obrigada"} for word in words[1:])
    return False


def _is_new_task_marker(prompt: str) -> bool:
    # The marker is an explicit user prefix, not text copied from quoted docs,
    # examples, or fenced source further into the prompt.
    return re.match(r"^\s*/new-task(?:\s|$)", prompt, flags=re.IGNORECASE) is not None


def _clear_followup(prompt: str, active: bool) -> bool:
    text = prompt.strip().casefold()
    if re.match(r"^(?:please\s+)?(?:continue|continua|continue com|continue a)\b", text):
        return True
    return active and bool(re.match(
        r"^(?:also\b|one more thing\b|isso inclui\b|e se\b)|"
        r"^(?:please\s+)?(?:add|include|adicione|inclua)\b[^\n]{0,250}\b(?:too|also|também|tambem)\s*[.!?]?$", text))


def _event_keys(event: BoundaryEvent) -> Tuple[str, ...]:
    # Include kind to keep same-turn lifecycle and prompt events distinct.
    # IDs are scoped by BoundaryScope because each state's receipts are local.
    keys = []
    prefix = event.kind.value + ":"
    # Multiple genuine native tasks can be created within one root turn. Their
    # stable task IDs, not the shared turn ID, define duplicate creation events.
    if event.kind is Lifecycle.TASK_CREATED and event.trusted_native and event.task_id:
        return (prefix + "native-task:" + event.task_id,)
    if event.event_id:
        keys.append(prefix + "event:" + event.event_id)
    if event.turn_id:
        keys.append(prefix + "turn:" + event.turn_id)
    return tuple(keys)


def _remember(state: BoundaryState, keys: Tuple[str, ...], cls: BoundaryClass,
              reason: str, task_id: Optional[str]) -> BoundaryState:
    if not keys:
        return state
    receipts = state.receipts + tuple(_Receipt(key, cls, reason, task_id) for key in keys)
    return _replace(state, receipts=receipts[-MAX_EVENT_HISTORY:])


def _replace(state: BoundaryState, **changes: object) -> BoundaryState:
    values = {
        "scope": state.scope,
        "status": state.status,
        "logical_task_id": state.logical_task_id,
        "native_task_id": state.native_task_id,
        "generation": state.generation,
        "next_task_number": state.next_task_number,
        "last_activity": state.last_activity,
        "objective_terms": state.objective_terms,
        "receipts": state.receipts,
        "warned_fingerprints": state.warned_fingerprints,
    }
    values.update(changes)
    return BoundaryState(**values)  # type: ignore[arg-type]


def mark_warning(state: BoundaryState, fingerprint: str) -> BoundaryState:
    """Record a bounded privacy-safe fingerprint for same-scope warning dedupe."""
    if not isinstance(fingerprint, str) or not fingerprint or len(fingerprint) > 256:
        raise ValueError("invalid warning fingerprint")
    if fingerprint in state.warned_fingerprints:
        return state
    return _replace(state, warned_fingerprints=(state.warned_fingerprints + (fingerprint,))[-MAX_WARNING_FINGERPRINTS:])


def transition(state: BoundaryState, event: BoundaryEvent, *, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> BoundaryTransition:
    """Apply one deterministic event; no global clock or provider is consulted.

    The caller supplies a monotonic timestamp. TTL expiry only discards stale
    evidence and yields UNKNOWN for that event; it is never itself a new-task
    signal. Lifecycle resume/compaction resets questionable task observations.
    """
    if not isinstance(state, BoundaryState) or not isinstance(event, BoundaryEvent):
        raise TypeError("boundary transition requires typed state and event")
    try:
        finite_ttl = math.isfinite(ttl_seconds)
    except (OverflowError, TypeError):
        finite_ttl = False
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)) or not finite_ttl or ttl_seconds <= 0:
        raise ValueError("invalid boundary TTL")

    if state.scope != event.scope:
        # Never carry task identity or warning dedupe across a different scope.
        state = initial_state(event.scope)
        return BoundaryTransition(state, BoundaryClass.UNKNOWN, "scope_changed")

    # Lifecycle resets must run before dedupe: a reused turn ID cannot make a
    # resume/compaction event disappear and leave questionable task state live.
    if event.kind in (Lifecycle.SESSION_START, Lifecycle.RESUME, Lifecycle.COMPACTION, Lifecycle.SESSION_END):
        reset = _replace(state, status=TaskStatus.IDLE if event.kind is Lifecycle.SESSION_START else TaskStatus.UNCERTAIN,
                         logical_task_id=None, native_task_id=None, objective_terms=(),
                         generation=state.generation + 1, last_activity=event.timestamp)
        return BoundaryTransition(reset, BoundaryClass.UNKNOWN, event.kind.value)

    keys = _event_keys(event)
    key_set = set(keys)
    if key_set and any(receipt.key in key_set for receipt in reversed(state.receipts)):
        # Concurrent hooks can acquire the state lock out of clock-sample order.
        # A known replay is not fresh evidence of a regressed clock or task.
        return BoundaryTransition(state, BoundaryClass.CONTINUATION,
                                  "duplicate_event", state.logical_task_id, True)

    if state.last_activity is not None and event.timestamp < state.last_activity:
        # A regressed injected clock invalidates stale task evidence but does
        # not roll time back or permit an automatic assessment.
        reset = _replace(state, status=TaskStatus.UNCERTAIN, logical_task_id=None,
                         native_task_id=None, objective_terms=())
        return BoundaryTransition(reset, BoundaryClass.UNKNOWN, "clock_regressed")

    stale = (state.last_activity is not None and
             event.timestamp - state.last_activity > ttl_seconds)
    if stale:
        state = _replace(state, status=TaskStatus.UNCERTAIN, logical_task_id=None,
                         native_task_id=None, objective_terms=(), last_activity=event.timestamp)

    if event.kind is Lifecycle.SUBAGENT_SPAWN:
        return BoundaryTransition(_replace(state, last_activity=event.timestamp),
                                  BoundaryClass.UNKNOWN, "child_task_not_root", state.logical_task_id)

    if event.kind in (Lifecycle.TOOL_ACTIVITY, Lifecycle.STOP):
        # A stop hook is not proof that the logical task completed.
        updated = _replace(state, last_activity=event.timestamp)
        return BoundaryTransition(updated, BoundaryClass.UNKNOWN,
                                  "tool_activity" if event.kind is Lifecycle.TOOL_ACTIVITY else "stop_not_completion",
                                  state.logical_task_id)

    if event.kind is Lifecycle.TASK_COMPLETED:
        if (event.trusted_native and event.task_id and
                event.task_id == state.native_task_id):
            closed = _replace(state, status=TaskStatus.COMPLETED, logical_task_id=None,
                              native_task_id=None, objective_terms=(), last_activity=event.timestamp)
            return BoundaryTransition(closed, BoundaryClass.UNKNOWN, "trusted_task_completed")
        return BoundaryTransition(_replace(state, last_activity=event.timestamp),
                                  BoundaryClass.UNKNOWN, "untrusted_or_unmatched_completion",
                                  state.logical_task_id)

    if event.kind is Lifecycle.TASK_CREATED:
        if not event.trusted_native or not event.task_id:
            updated = _replace(state, status=TaskStatus.UNCERTAIN, last_activity=event.timestamp)
            return BoundaryTransition(_remember(updated, keys, BoundaryClass.UNKNOWN,
                                                "untrusted_task_created", state.logical_task_id),
                                      BoundaryClass.UNKNOWN, "untrusted_task_created", state.logical_task_id)
        if (state.logical_task_id and
                (event.task_id == state.native_task_id or event.linked_task_id == state.native_task_id)):
            updated = _replace(state, status=TaskStatus.ACTIVE, last_activity=event.timestamp)
            return BoundaryTransition(_remember(updated, keys, BoundaryClass.CONTINUATION,
                                                "same_native_task", state.logical_task_id),
                                      BoundaryClass.CONTINUATION, "same_native_task", state.logical_task_id)
        return _new_task(state, event, keys, "trusted_task_created", native_task_id=event.task_id)

    if event.kind is Lifecycle.PREFLIGHT:
        return _new_task(state, event, keys, "explicit_preflight")

    if event.kind is not Lifecycle.USER_PROMPT:
        return BoundaryTransition(_replace(state, last_activity=event.timestamp),
                                  BoundaryClass.UNKNOWN, "unsupported_event", state.logical_task_id)

    if ((event.linked_task_id and event.linked_task_id == state.native_task_id) or
            (event.task_id and event.task_id == state.native_task_id)):
        updated = _replace(state, status=TaskStatus.ACTIVE, last_activity=event.timestamp)
        return _record_transition(updated, keys, BoundaryClass.CONTINUATION,
                                  "linked_same_task", state.logical_task_id)
    if _is_ack(event.prompt):
        updated = _replace(state, status=TaskStatus.ACTIVE if state.logical_task_id else state.status,
                           last_activity=event.timestamp)
        return _record_transition(updated, keys, BoundaryClass.CONTINUATION,
                                  "clear_acknowledgement", state.logical_task_id)
    if _clear_followup(event.prompt, state.logical_task_id is not None):
        updated = _replace(state, last_activity=event.timestamp)
        return _record_transition(updated, keys, BoundaryClass.CONTINUATION,
                                  "explicit_followup", state.logical_task_id)
    if _is_new_task_marker(event.prompt):
        return _new_task(state, event, keys, "explicit_new_task_marker")

    terms = _content_terms(event.prompt)
    # An explicit new-objective request can concern the same repository and
    # vocabulary. Requiring disjoint terms would miss clearly stated new tasks.
    if _explicit_topic_shift(event.prompt) and _standalone(event.prompt, terms):
        return _new_task(state, event, keys, "explicit_topic_shift", terms=terms)

    if stale:
        # Expiration is not proof of a new objective. Require a later event or
        # explicit structural signal rather than classifying on the TTL edge.
        updated = _replace(state, status=TaskStatus.UNCERTAIN, last_activity=event.timestamp)
        return _record_transition(updated, keys, BoundaryClass.UNKNOWN, "ttl_expired", None)

    if not _standalone(event.prompt, terms):
        updated = _replace(state, status=TaskStatus.UNCERTAIN if state.status is not TaskStatus.ACTIVE else state.status,
                           last_activity=event.timestamp)
        return _record_transition(updated, keys, BoundaryClass.UNKNOWN, "ambiguous_prompt", state.logical_task_id)

    if state.status in (TaskStatus.IDLE, TaskStatus.COMPLETED) or not state.logical_task_id:
        return _new_task(state, event, keys, "standalone_initial_objective", terms=terms)

    updated = _replace(state, last_activity=event.timestamp)
    return _record_transition(updated, keys, BoundaryClass.UNKNOWN, "objective_change_not_proven",
                              state.logical_task_id)


def _new_task(state: BoundaryState, event: BoundaryEvent, keys: Tuple[str, ...], reason: str,
              *, native_task_id: Optional[str] = None,
              terms: Optional[Tuple[str, ...]] = None) -> BoundaryTransition:
    if not keys:
        return BoundaryTransition(state, BoundaryClass.UNKNOWN, "missing_event_identity",
                                  state.logical_task_id)
    material = json.dumps((event.scope.runtime, event.scope.project_id,
                           event.scope.session_id, state.next_task_number),
                          ensure_ascii=True, separators=(",", ":"))
    logical_id = "root-" + hashlib.sha256(material.encode("ascii")).hexdigest()
    updated = _replace(state, status=TaskStatus.ACTIVE, logical_task_id=logical_id,
                       native_task_id=native_task_id, next_task_number=state.next_task_number + 1,
                       last_activity=event.timestamp,
                       objective_terms=terms if terms is not None else ())
    updated = _remember(updated, keys, BoundaryClass.NEW_TASK, reason, logical_id)
    return BoundaryTransition(updated, BoundaryClass.NEW_TASK, reason, logical_id)


def _record_transition(state: BoundaryState, keys: Tuple[str, ...], cls: BoundaryClass,
                       reason: str, logical_id: Optional[str]) -> BoundaryTransition:
    updated = _remember(state, keys, cls, reason, logical_id)
    return BoundaryTransition(updated, cls, reason, logical_id)

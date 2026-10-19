"""Private bounded cross-process state (RTE-020).

A claim is durably written *before* invoking a classifier. Failed/interrupted
claims are never retried inside their retention window: missing a route is safer
than classifying twice. This is at-most-once execution, not exactly-once success.
Only typed decisions, hashes, counters and bounded boundary metadata go to disk.
The store is not a security boundary against code already running as its owner.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from enum import Enum
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import time
from typing import Callable, Optional

from . import boundary
from .contracts import RouteDecision
from .snapshots import VersionSnapshot

StateScope = boundary.BoundaryScope
_HEX = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^router_[0-9a-f]{48}$")
_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_LOGICAL = re.compile(r"^root-[0-9a-f]{64}$")
_MAX_TTL = 86400.0
_STATE = "state.json"
_LOCK = "state.lock"


class StateError(Exception):
    """Stable diagnostic; never includes paths, identifiers or caught errors."""
    CODES = frozenset({"unsafe_path", "state_io", "invalid_state", "capacity",
                       "lock_timeout", "invalid_input", "callback_failed", "clock_regressed"})

    def __init__(self, code: str):
        self.code = code if code in self.CODES else "state_io"
        super().__init__(self.code)


class StateDisposition(str, Enum):
    COMPUTED = "computed"
    CACHED = "cached"
    INFLIGHT = "inflight"
    ERROR = "error"


@dataclass(frozen=True)
class StateResult:
    disposition: StateDisposition
    decision: Optional[RouteDecision] = None
    error: Optional[StateError] = None


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _scope_hash(scope: StateScope) -> str:
    if not isinstance(scope, StateScope):
        raise StateError("invalid_input")
    return _digest(json.dumps([scope.runtime, scope.project_id, scope.session_id],
                              ensure_ascii=True, separators=(",", ":")))


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise StateError("invalid_input")
    return _digest(value)


def _number(value, minimum=0, maximum=None):
    if (type(value) not in (float, int) or not math.isfinite(value) or value < minimum
            or (maximum is not None and value > maximum)):
        raise StateError("invalid_state")
    return value


def _exact(obj, fields):
    if not isinstance(obj, dict) or set(obj) != set(fields):
        raise StateError("invalid_state")


def _hash(value):
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise StateError("invalid_state")
    return value


def _decision_dict(decision):
    if not isinstance(decision, RouteDecision):
        raise StateError("invalid_input")
    obj = decision.to_dict()
    # Contracts permit arbitrary strings for in-memory interchange; persistence
    # is deliberately narrower. In particular no provider prose/raw response.
    for name, value in obj.items():
        if isinstance(value, str) and not _LABEL.fullmatch(value):
            raise StateError("invalid_input")
    return obj


def _decision_load(obj):
    try:
        decision = RouteDecision.from_dict(obj)
        if _decision_dict(decision) != obj:
            raise StateError("invalid_state")
        return decision
    except (ValueError, TypeError, StateError):
        raise StateError("invalid_state") from None


def _unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise StateError("invalid_state")
        obj[key] = value
    return obj


def _boundary_dump(state):
    return {"status": state.status.value, "logical_task_id": state.logical_task_id,
            "native_task_id": state.native_task_id, "generation": state.generation,
            "next_task_number": state.next_task_number, "last_activity": state.last_activity,
            "objective_terms": list(state.objective_terms),
            "receipts": [{"key": r.key, "classification": r.task_class.value,
                          "reason": r.reason, "logical_task_id": r.logical_task_id}
                         for r in state.receipts],
            "warned_fingerprints": list(state.warned_fingerprints)}


def _boundary_load(obj, scope):
    _exact(obj, {"status", "logical_task_id", "native_task_id", "generation", "next_task_number",
                 "last_activity", "objective_terms", "receipts", "warned_fingerprints"})
    for name in ("logical_task_id",):
        if obj[name] is not None and (not isinstance(obj[name], str) or not _LOGICAL.fullmatch(obj[name])):
            raise StateError("invalid_state")
    if obj["native_task_id"] is not None:
        _hash(obj["native_task_id"])
    for name, lower in (("generation", 0), ("next_task_number", 1)):
        if type(obj[name]) is not int or not lower <= obj[name] <= 2**53:
            raise StateError("invalid_state")
    if obj["last_activity"] is not None:
        _number(obj["last_activity"])
    terms = obj["objective_terms"]
    warnings = obj["warned_fingerprints"]
    receipts = obj["receipts"]
    if (not isinstance(terms, list) or len(terms) > boundary.MAX_OBJECTIVE_TERMS or
            any(not isinstance(t, str) or not re.fullmatch(r"[0-9a-f]{32}", t) for t in terms)
            or not isinstance(warnings, list) or len(warnings) > boundary.MAX_WARNING_FINGERPRINTS
            or not isinstance(receipts, list) or len(receipts) > boundary.MAX_EVENT_HISTORY):
        raise StateError("invalid_state")
    for fingerprint in warnings:
        _hash(fingerprint)
    parsed = []
    for receipt in receipts:
        _exact(receipt, {"key", "classification", "reason", "logical_task_id"})
        key = receipt["key"]
        if not isinstance(key, str) or not re.fullmatch(
                r"[a-z_]+:(?:event|turn|native-task):[0-9a-f]{64}", key):
            raise StateError("invalid_state")
        if not isinstance(receipt["reason"], str) or not re.fullmatch(r"[a-z_]{1,80}", receipt["reason"]):
            raise StateError("invalid_state")
        logical = receipt["logical_task_id"]
        if logical is not None and (not isinstance(logical, str) or not _LOGICAL.fullmatch(logical)):
            raise StateError("invalid_state")
        parsed.append(boundary._Receipt(key, boundary.BoundaryClass(receipt["classification"]),
                                        receipt["reason"], logical))
    return boundary.BoundaryState(scope, boundary.TaskStatus(obj["status"]),
        obj["logical_task_id"], obj["native_task_id"], obj["generation"], obj["next_task_number"],
        obj["last_activity"], tuple(terms), tuple(parsed), tuple(warnings))


class PrivateStateStore:
    """One private atomic JSON transaction with a bounded POSIX advisory lock.

    root's parent must exist. Root must be owner-only (0700); existing unsafe
    modes are rejected, never silently repaired. Files must be owned, regular,
    single-link 0600 files. No lock is held during a potentially slow callback.
    """
    def __init__(self, root, *, ttl_seconds=1800, max_records=1024,
                 max_bytes=1024 * 1024, lock_wait_seconds=0.5, clock=time.time):
        try:
            self.root = Path(os.path.abspath(os.fspath(root)))
            if not 0 < _number(ttl_seconds, maximum=_MAX_TTL):
                raise ValueError()
            if type(max_records) is not int or not 1 <= max_records <= 10000:
                raise ValueError()
            if type(max_bytes) is not int or not 1024 <= max_bytes <= 16 * 1024 * 1024:
                raise ValueError()
            _number(lock_wait_seconds, maximum=10)
            if not callable(clock) or self.root == Path("/"):
                raise ValueError()
        except (TypeError, ValueError, OverflowError, StateError):
            raise StateError("invalid_input") from None
        self.ttl_seconds = float(ttl_seconds)
        self.max_records = max_records
        self.max_bytes = max_bytes
        self.lock_wait_seconds = float(lock_wait_seconds)
        self.clock = clock

    @staticmethod
    def _check_dir(st, *, private=False):
        mode = stat.S_IMODE(st.st_mode)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid not in (0, os.getuid()):
            raise StateError("unsafe_path")
        if private:
            if st.st_uid != os.getuid() or mode != 0o700:
                raise StateError("unsafe_path")
        elif mode & 0o022 and not (st.st_uid == 0 and mode & stat.S_ISVTX):
            raise StateError("unsafe_path")

    def _open_root(self, *, create=True):
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            # Anchor every operation to directory descriptors. Allow only
            # immutable root-owned system aliases (macOS /var -> /private/var),
            # never user-controlled symlink ancestors or a symlink root.
            for component in self.root.parts[1:-1]:
                st = os.stat(component, dir_fd=fd, follow_symlinks=False)
                flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                if stat.S_ISLNK(st.st_mode):
                    parent = os.fstat(fd)
                    if st.st_uid != 0 or parent.st_uid != 0 or stat.S_IMODE(parent.st_mode) & 0o022:
                        raise StateError("unsafe_path")
                    flags &= ~os.O_NOFOLLOW
                child = os.open(component, flags, dir_fd=fd)
                os.close(fd)
                fd = child
                self._check_dir(os.fstat(fd))
            if create:
                try:
                    os.mkdir(self.root.name, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(self.root.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                self._check_dir(os.fstat(child), private=True)
            except BaseException:
                os.close(child)
                raise
            return child
        finally:
            os.close(fd)

    @staticmethod
    def _check_file(fd):
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or
                stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1):
            raise StateError("unsafe_path")
        return st

    @contextmanager
    def _read_lock(self):
        """Existing private root/lock only; no mkdir, creation or temp cleanup.

        None denotes uninitialized storage. A data file without its lock inode
        is unsafe, not permission to recreate synchronization while reading.
        """
        rootfd = lockfd = None
        try:
            try:
                rootfd = self._open_root(create=False)
            except FileNotFoundError:
                yield None
                return
            try:
                lockfd = os.open(_LOCK, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=rootfd)
            except FileNotFoundError:
                for name in (_STATE, "telemetry.jsonl", "telemetry.1.jsonl", "telemetry.2.jsonl"):
                    try:
                        os.stat(name, dir_fd=rootfd, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    raise StateError("unsafe_path")
                yield None
                return
            st = self._check_file(lockfd)
            deadline = time.monotonic() + self.lock_wait_seconds
            while True:
                try:
                    fcntl.flock(lockfd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise StateError("lock_timeout") from None
                    time.sleep(min(0.005, max(0, deadline - time.monotonic())))
            named = os.stat(_LOCK, dir_fd=rootfd, follow_symlinks=False)
            if (named.st_dev, named.st_ino) != (st.st_dev, st.st_ino):
                raise StateError("unsafe_path")
            yield rootfd
        except StateError:
            raise
        except (OSError, ValueError, TypeError, OverflowError, RecursionError):
            raise StateError("state_io") from None
        finally:
            if lockfd is not None:
                os.close(lockfd)
            if rootfd is not None:
                os.close(rootfd)

    def read_snapshots(self, scope_hash, snapshot_ids):
        """Read immutable retained metadata by hashes without state mutation.

        Missing/expired values are None. No provider/credential/runtime/config
        reads. Batch lookup uses a single bounded shared lock; expired records
        are filtered only in memory, never persisted or cleaned here.
        """
        if (not isinstance(scope_hash, str) or not _HEX.fullmatch(scope_hash)
                or not isinstance(snapshot_ids, (list, tuple, set, frozenset)) or len(snapshot_ids) > 50
                or any(not isinstance(s, str) or not _HEX.fullmatch(s) for s in snapshot_ids)):
            raise StateError("invalid_input")
        result = dict.fromkeys(snapshot_ids)
        if not result:
            return result
        with self._read_lock() as fd:
            if fd is None:
                return result
            now = float(_number(self.clock()))
            data = self._read(fd, now)
            for snapshot_id in result:
                key = self._key("snapshot", scope_hash, _identifier(snapshot_id))
                record = data["records"].get(key)
                if record is not None:
                    snapshot = VersionSnapshot.from_dict(record["value"])
                    if snapshot.snapshot_id != snapshot_id:
                        raise StateError("invalid_state")
                    result[snapshot_id] = snapshot
        return result

    @contextmanager
    def _transaction(self):
        rootfd = lockfd = None
        try:
            rootfd = self._open_root()
            flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
            # Publish once, then open existing. Concurrent macOS O_CREAT opens
            # without O_EXCL occasionally returned ENOENT in the first-use
            # stress test. Never recreate an existing lock after it disappears:
            # that could split synchronization across two inodes.
            try:
                lockfd = os.open(_LOCK, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=rootfd)
            except FileExistsError:
                lockfd = os.open(_LOCK, flags, dir_fd=rootfd)
            lockstat = self._check_file(lockfd)
            deadline = time.monotonic() + self.lock_wait_seconds
            while True:
                try:
                    fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise StateError("lock_timeout") from None
                    time.sleep(min(0.005, max(0, deadline - time.monotonic())))
            named = os.stat(_LOCK, dir_fd=rootfd, follow_symlinks=False)
            if (named.st_dev, named.st_ino) != (lockstat.st_dev, lockstat.st_ino):
                raise StateError("unsafe_path")
            self._cleanup_temporaries(rootfd)
            now = float(_number(self.clock()))
            data = self._read(rootfd, now)
            yield rootfd, data, now
        except StateError:
            raise
        except (OSError, ValueError, TypeError, OverflowError, RecursionError):
            raise StateError("state_io") from None
        finally:
            if lockfd is not None:
                os.close(lockfd)
            if rootfd is not None:
                os.close(rootfd)

    def _cleanup_temporaries(self, rootfd):
        # Interrupted atomic writes must not accumulate indefinitely. No other
        # legitimate writer can be using these files while this lock is held.
        with os.scandir(rootfd) as entries:
            for index, entry in enumerate(entries):
                if index >= 128:
                    raise StateError("capacity")
                if re.fullmatch(r"\.tmp-[0-9a-f]{32}", entry.name):
                    fd = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=rootfd)
                    try:
                        self._check_file(fd)
                    finally:
                        os.close(fd)
                    os.unlink(entry.name, dir_fd=rootfd)

    def _read(self, rootfd, now):
        try:
            fd = os.open(_STATE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=rootfd)
        except FileNotFoundError:
            return {"schema": 1, "last_write": now, "records": {}}
        try:
            st = self._check_file(fd)
            if st.st_size > self.max_bytes:
                raise StateError("capacity")
            chunks = []
            remaining = self.max_bytes + 1
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > self.max_bytes:
                raise StateError("capacity")
        finally:
            os.close(fd)
        try:
            data = json.loads(raw, object_pairs_hook=_unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(StateError("invalid_state")))
            _exact(data, {"schema", "last_write", "records"})
            if type(data["schema"]) is not int or data["schema"] != 1:
                raise StateError("invalid_state")
            if _number(data["last_write"]) > now:
                raise StateError("clock_regressed")
            records = data["records"]
            if not isinstance(records, dict) or len(records) > self.max_records:
                raise StateError("capacity")
            for key, record in records.items():
                _hash(key)
                _exact(record, {"kind", "scope", "subject", "created", "expires", "value"})
                _hash(record["scope"])
                _hash(record["subject"])
                kind = record["kind"]
                if kind not in ("decision", "prepared", "boundary", "root", "snapshot") or key != self._key(kind, record["scope"], record["subject"]):
                    raise StateError("invalid_state")
                created = _number(record["created"])
                expires = _number(record["expires"])
                if created > now or not 0 < expires - created <= _MAX_TTL:
                    raise StateError("invalid_state")
                value = record["value"]
                if kind == "decision":
                    _exact(value, {"claim", "decision", "failed"})
                    _hash(value["claim"])
                    if type(value["failed"]) is not bool or (value["failed"] and value["decision"] is not None):
                        raise StateError("invalid_state")
                    if value["decision"] is not None:
                        _decision_load(value["decision"])
                elif kind == "prepared":
                    if expires - created > 300:
                        raise StateError("invalid_state")
                    _decision_load(value)
                elif kind == "snapshot":
                    snapshot = VersionSnapshot.from_dict(value)
                    if record["subject"] != _identifier(snapshot.snapshot_id):
                        raise StateError("invalid_state")
                elif kind == "root":
                    _exact(value, {"model", "effort"})
                    for item in value.values():
                        if item is not None and (not isinstance(item, str) or not _LABEL.fullmatch(item)):
                            raise StateError("invalid_state")
                else:
                    # No stored raw scope is needed to validate the metadata.
                    _boundary_load(value, StateScope("claude", "validation", "validation"))
            data["records"] = {k: v for k, v in records.items() if v["expires"] > now}
            return data
        except StateError:
            raise
        except (ValueError, TypeError, UnicodeError, KeyError, OverflowError, RecursionError):
            raise StateError("invalid_state") from None

    @staticmethod
    def _key(kind, scope_hash, subject):
        return _digest(kind + ":" + scope_hash + ":" + subject)

    def _insert(self, data, kind, scope_hash, subject, value, now, ttl):
        key = self._key(kind, scope_hash, subject)
        if key not in data["records"] and len(data["records"]) >= self.max_records:
            raise StateError("capacity")
        if not math.isfinite(now + ttl) or now + ttl <= now:
            raise StateError("invalid_input")
        data["records"][key] = {"kind": kind, "scope": scope_hash, "subject": subject,
            "created": now, "expires": now + ttl, "value": value}
        return key

    def _write(self, rootfd, data, now):
        data["last_write"] = now
        raw = json.dumps(data, separators=(",", ":"), allow_nan=False).encode("ascii")
        if len(raw) > self.max_bytes:
            raise StateError("capacity")
        name = ".tmp-" + secrets.token_hex(16)
        fd = None
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=rootfd)
            self._check_file(fd)
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                if not written:
                    raise StateError("state_io")
                view = view[written:]
            os.fsync(fd)
            os.close(fd)
            fd = None
            os.replace(name, _STATE, src_dir_fd=rootfd, dst_dir_fd=rootfd)
            os.fsync(rootfd)
        finally:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(name, dir_fd=rootfd)
            except FileNotFoundError:
                pass

    def run_once(self, scope, tool_call_id, callback: Callable[[], RouteDecision]) -> StateResult:
        try:
            scope_hash, subject = _scope_hash(scope), _identifier(tool_call_id)
            if not callable(callback):
                raise StateError("invalid_input")
            key = self._key("decision", scope_hash, subject)
            claim = secrets.token_hex(32)
            with self._transaction() as (fd, data, now):
                record = data["records"].get(key)
                if record:
                    value = record["value"]
                    if value["decision"] is not None:
                        return StateResult(StateDisposition.CACHED, _decision_load(value["decision"]))
                    if value["failed"]:
                        return StateResult(StateDisposition.ERROR, error=StateError("callback_failed"))
                    return StateResult(StateDisposition.INFLIGHT)
                self._insert(data, "decision", scope_hash, subject,
                             {"claim": claim, "decision": None, "failed": False}, now, self.ttl_seconds)
                self._write(fd, data, now)
            try:
                decision = callback()
                encoded = _decision_dict(decision)
            except Exception:
                # Never serialize exception text or retry this claimed event.
                self._finish(key, claim, None, True)
                return StateResult(StateDisposition.ERROR, error=StateError("callback_failed"))
            if not self._finish(key, claim, encoded, False):
                return StateResult(StateDisposition.ERROR, error=StateError("state_io"))
            return StateResult(StateDisposition.COMPUTED, decision)
        except StateError as exc:
            return StateResult(StateDisposition.ERROR, error=exc)

    def _finish(self, key, claim, decision, failed):
        with self._transaction() as (fd, data, now):
            record = data["records"].get(key)
            if record is None or record["value"]["claim"] != claim:
                return False
            record["value"] = {"claim": claim, "decision": decision, "failed": failed}
            self._write(fd, data, now)
            return True

    def issue_prepared(self, scope, decision, ttl_seconds=300):
        scope_hash = _scope_hash(scope)
        if type(ttl_seconds) not in (int, float) or not math.isfinite(ttl_seconds) or not 0 < ttl_seconds <= 300:
            raise StateError("invalid_input")
        encoded = _decision_dict(replace(decision, provenance="orchestrator_attested")) if isinstance(decision, RouteDecision) else None
        if encoded is None:
            raise StateError("invalid_input")
        reference = "router_" + secrets.token_hex(24)
        with self._transaction() as (fd, data, now):
            self._insert(data, "prepared", scope_hash, _digest(reference), encoded, now, ttl_seconds)
            self._write(fd, data, now)
        return reference

    def consume_prepared(self, scope, reference):
        scope_hash = _scope_hash(scope)
        if not isinstance(reference, str) or not _REF.fullmatch(reference):
            return None
        key = self._key("prepared", scope_hash, _digest(reference))
        with self._transaction() as (fd, data, now):
            record = data["records"].pop(key, None)
            if record is None:
                return None
            decision = _decision_load(record["value"])
            self._write(fd, data, now)
            return decision

    def _boundary_record(self, data, scope):
        sh = _scope_hash(scope)
        key = self._key("boundary", sh, _digest("boundary"))
        record = data["records"].get(key)
        state = _boundary_load(record["value"], scope) if record else boundary.initial_state(scope)
        return sh, state

    def get_boundary(self, scope):
        with self._transaction() as (_, data, _now):
            return self._boundary_record(data, scope)[1]

    def apply_boundary(self, event, *, root_observation=None):
        if not isinstance(event, boundary.BoundaryEvent):
            raise StateError("invalid_input")
        if root_observation is not None:
            if not isinstance(root_observation, dict) or set(root_observation) != {"model", "effort"}:
                raise StateError("invalid_input")
            for value in root_observation.values():
                if value is not None and (not isinstance(value, str) or not _LABEL.fullmatch(value)):
                    raise StateError("invalid_input")
        # Hash every native identity consistently before the pure machine sees
        # it; receipts and completion/link comparisons therefore remain valid.
        changes = {name: _identifier(getattr(event, name)) if getattr(event, name) is not None else None
                   for name in ("event_id", "turn_id", "task_id", "linked_task_id")}
        safe_event = replace(event, **changes)
        with self._transaction() as (fd, data, now):
            sh, state = self._boundary_record(data, event.scope)
            if event.kind in (boundary.Lifecycle.SESSION_START, boundary.Lifecycle.RESUME,
                              boundary.Lifecycle.COMPACTION, boundary.Lifecycle.SESSION_END):
                data["records"].pop(self._key("root", sh, _digest("root")), None)
            result = boundary.transition(state, safe_event, ttl_seconds=self.ttl_seconds)
            encoded = _boundary_dump(result.state)
            _boundary_load(encoded, event.scope)
            self._insert(data, "boundary", sh, _digest("boundary"), encoded, now, self.ttl_seconds)
            # Transition and associated host observation are one commit. A late
            # duplicate/regressed event must not overwrite a newer model switch.
            if root_observation is not None and not result.duplicate and result.reason != "clock_regressed":
                self._insert(data, "root", sh, _digest("root"), dict(root_observation), now, self.ttl_seconds)
            self._write(fd, data, now)
            return result

    def claim_warning(self, scope, fingerprint, *, task_id=None, root_observation=None):
        """Claim delivery, optionally guarded by the still-current root task/route.

        The guarded form prevents slow classification from delivering advice
        after a model switch, compaction, or newer task won the state race.
        """
        digest = _identifier(fingerprint)
        if (task_id is None) != (root_observation is None):
            raise StateError("invalid_input")
        if task_id is not None:
            if not isinstance(task_id, str) or not _LOGICAL.fullmatch(task_id):
                raise StateError("invalid_input")
            if not isinstance(root_observation, dict) or set(root_observation) != {"model", "effort"}:
                raise StateError("invalid_input")
            for value in root_observation.values():
                if value is not None and (not isinstance(value, str) or not _LABEL.fullmatch(value)):
                    raise StateError("invalid_input")
        with self._transaction() as (fd, data, now):
            sh, state = self._boundary_record(data, scope)
            if task_id is not None:
                root = data["records"].get(self._key("root", sh, _digest("root")))
                if state.logical_task_id != task_id or root is None or root["value"] != root_observation:
                    return False
            if digest in state.warned_fingerprints:
                return False
            updated = boundary.mark_warning(state, digest)
            self._insert(data, "boundary", sh, _digest("boundary"), _boundary_dump(updated), now, self.ttl_seconds)
            self._write(fd, data, now)
            return True

    def mark_warning(self, scope, fingerprint):
        self.claim_warning(scope, fingerprint)
        return self.get_boundary(scope)

    def observe_root(self, scope, *, model=None, effort=None):
        """Persist only adapter-attested host observations, never config guesses."""
        sh = _scope_hash(scope)
        for value in (model, effort):
            if value is not None and (not isinstance(value, str) or not _LABEL.fullmatch(value)):
                raise StateError("invalid_input")
        with self._transaction() as (fd, data, now):
            self._insert(data, "root", sh, _digest("root"), {"model": model, "effort": effort}, now, self.ttl_seconds)
            self._write(fd, data, now)

    def get_root(self, scope):
        sh = _scope_hash(scope)
        with self._transaction() as (_, data, _now):
            record = data["records"].get(self._key("root", sh, _digest("root")))
            return dict(record["value"]) if record else {"model": None, "effort": None}

    def put_snapshot(self, scope, snapshot):
        """Persist immutable metadata before a decision/provider request.

        Retain at least as long as decisions/prepared references. Capacity and
        permissions use the same bounded private transactional store.
        """
        if not isinstance(snapshot, VersionSnapshot):
            raise StateError("invalid_input")
        sh = _scope_hash(scope)
        with self._transaction() as (fd, data, now):
            self._insert(data, "snapshot", sh, _identifier(snapshot.snapshot_id),
                         snapshot.to_dict(), now, _MAX_TTL)
            self._write(fd, data, now)
        return snapshot.snapshot_id

    def get_snapshot(self, scope, snapshot_id):
        if not isinstance(snapshot_id, str) or not _HEX.fullmatch(snapshot_id):
            raise StateError("invalid_input")
        sh = _scope_hash(scope)
        with self._transaction() as (_, data, _now):
            record = data["records"].get(self._key("snapshot", sh, _identifier(snapshot_id)))
            return VersionSnapshot.from_dict(record["value"]) if record else None

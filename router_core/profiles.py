"""Private operator capability profiles, live-bound to effective hook metadata.

No project config may grant this authority. Owner-controlled files are not a
security boundary against their owner. Hook inventories are checked, not trusted
from booleans in JSON; arbitrary commands/prose are never saved in a profile.
"""
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shlex
import stat
import sys
import time

from .catalog import CatalogRegistry
from .classifier import _unique
from .config import DEFAULT_CONFIG
from .inventory import read_codex_hooks
from .native import bootstrap_profile
from .snapshots import VersionSnapshot
from .state import PrivateStateStore

ROOT = Path(__file__).resolve().parents[1]
MAX_PROFILE_BYTES = 262144
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = {"schema_version", "runtime", "surface", "host_version", "project_hash", "source_project_hash",
           "binary_identity", "implementation_sha256", "hook_digest", "created_at", "expires_at", "catalog"}


class ProfileError(ValueError):
    """Stable sanitized reason only, never paths, commands or file content."""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _project(path):
    # Filesystem scope is canonical, native hook source spelling is not.
    source = os.path.abspath(os.fspath(path))
    return _hash(os.path.realpath(source)), _hash(source)


def implementation_digest():
    digest = hashlib.sha256()
    paths = sorted((ROOT/"router_core").glob("*.py")) + [ROOT/"scripts/router_hook.py", ROOT/"scripts/router_mcp.py"]
    total = 0
    for path in paths:
        raw = path.read_bytes()
        total += len(raw)
        if total > 2_097_152:
            raise ProfileError("implementation_size_limit")
        digest.update(str(path.relative_to(ROOT)).encode("utf-8") + b"\0" + raw + b"\0")
    return digest.hexdigest()


def binary_identity(binary):
    if not isinstance(binary, str) or not os.path.isabs(binary):
        raise ProfileError("invalid_binary")
    path = os.path.realpath(binary)
    info = os.stat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or not os.access(path, os.X_OK):
        raise ProfileError("unsafe_binary")
    # Version is independently verified by the public metadata client. This
    # inexpensive identity detects upgrades without rehashing a large binary
    # for every tool hook; not a signature/security boundary against its owner.
    return _hash(_json([path, info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]))


def _overlaps(matcher, targets):
    if matcher in (None, "", "*"):
        return True
    if not isinstance(matcher, str) or len(matcher) > 1024:
        return True
    # Only execute a small linear-time subset. Unknown regex may overlap.
    # Validation must preserve regex search semantics (not literal equality).
    text = matcher.removeprefix("^").removesuffix("$")
    if text.startswith("(?:") and text.endswith(")"):
        text = text[3:-1]
    pieces = text.split("|")
    for piece in pieces:
        piece = piece.removeprefix("^").removesuffix("$")
        prefix = piece.endswith(".*")
        # A single terminal literal-character repetition (e.g. Engram's
        # mem_*) is also linear-time. Keep its actual regex meaning: it repeats
        # only the last character, NOT a glob wildcard. No interior/nested
        # repetitions are accepted by the literal grammar below.
        literal = piece[:-2] if prefix else piece[:-1] if piece.endswith("*") else piece
        if re.fullmatch(r"(?:[A-Za-z0-9_:/-]|\\\.)+", literal) is None:
            return True
    return any(re.search(matcher, target) is not None for target in targets)


def _own_command(command, *, runtime, surface, project, binary, profile_path,
                 source=None, source_path=None, plugin_id=None):
    try:
        # The sole accepted variable token uses real shell ENV expansion, not
        # Codex's unsafe pre-shell ${PLUGIN_ROOT} text replacement. Bind it to
        # this installed code's exact hook source and plugin identity before
        # normalizing for the existing strict argv recognizer.
        root_token = '"$PLUGIN_ROOT/scripts/router_hook.py"'
        if isinstance(command, str) and root_token in command:
            if (source != "plugin" or not isinstance(plugin_id, str)
                    or not plugin_id.startswith("intelligent-agent-router@")
                    or not isinstance(source_path, str) or not os.path.isabs(source_path)
                    or os.path.realpath(source_path) != str(ROOT/"hooks/hooks.json")
                    or command.count(root_token) != 1):
                return False
            command = command.replace(root_token, shlex.quote(str(ROOT/"scripts/router_hook.py")), 1)
        # shlex tokenization alone does not rule out shell expansion/execution.
        # Deliberately reject even quoted metacharacters: unusual literal paths
        # remain advisory rather than granting authority to ambiguous commands.
        if not isinstance(command, str) or any(c in command for c in "$`\n\r;|&<>()\\"):
            return False
        tokens = shlex.split(command)
        if len(tokens) < 4 or (len(tokens)-2) % 2:
            return False
        if os.path.realpath(tokens[0]) != os.path.realpath(sys.executable) or not os.path.isabs(tokens[0]):
            return False
        if os.path.realpath(tokens[1]) != str(ROOT/"scripts/router_hook.py") or not os.path.isabs(tokens[1]):
            return False
        args = {}
        allowed = {"--runtime", "--surface", "--runtime-binary", "--project", "--scope", "--global-config", "--state-dir", "--key-file", "--capability-profile"}
        for key, value in zip(tokens[2::2], tokens[3::2]):
            if key not in allowed or key in args:
                return False
            if key not in {"--runtime", "--surface", "--scope"} and not os.path.isabs(value):
                return False
            args[key] = value
        if args.get("--scope") == "global":
            from .global_scope import profile_path as global_profile_path
            # Global scope is recognized only for this exact installed plugin.
            scoped = ("--project" not in args and source == "plugin"
                and isinstance(plugin_id, str) and plugin_id.startswith("intelligent-agent-router@")
                and isinstance(source_path, str) and os.path.realpath(source_path) == str(ROOT/"hooks/hooks.json")
                and os.path.abspath(global_profile_path(args["--capability-profile"], project)) == os.path.abspath(profile_path))
        else:
            scoped = "--scope" not in args and _project(args["--project"]) == _project(project)
        return (args.get("--runtime") == runtime and args.get("--surface") == surface
                and scoped
                and os.path.realpath(args["--runtime-binary"]) == os.path.realpath(binary)
                and (args.get("--scope") == "global" or os.path.abspath(args["--capability-profile"]) == os.path.abspath(profile_path)))
    except Exception:
        return False


def analyze_hooks(hooks, *, runtime, surface, project, binary, profile_path):
    try:
        if not isinstance(hooks, list) or len(hooks) > 1024 or any(not isinstance(h, dict) or not isinstance(h.get("key"), str) for h in hooks):
            raise ValueError()
        if len({h["key"] for h in hooks}) != len(hooks):
            raise ValueError()
        digest = _hash(_json(sorted(hooks, key=lambda h: h["key"])))
        targets = ("spawn_agent", "collaboration.spawn_agent", "collaborationspawn_agent", "Agent", "Task")
        own, reasons = 0, []
        for hook in hooks:
            if hook.get("eventName") != "preToolUse" or hook.get("enabled") is False:
                continue
            if not _overlaps(hook.get("matcher"), targets):
                continue
            if hook.get("enabled") is not True or hook.get("trustStatus") not in ("trusted", "managed"):
                reasons.append("matching_hook_needs_review")
            elif (hook.get("handlerType") != "command" or hook.get("async") is not False
                  or not _own_command(hook.get("command"), runtime=runtime, surface=surface,
                                      project=project, binary=binary, profile_path=profile_path,
                                      source=hook.get("source"), source_path=hook.get("sourcePath"),
                                      plugin_id=hook.get("pluginId"))):
                reasons.append("competing_or_unknown_rewrite")
            else:
                own += 1
        if own != 1:
            reasons.append("router_hook_missing_or_duplicated")
        return {"hook_digest": digest, "safe": not reasons, "reason_codes": sorted(set(reasons)), "matching_router_hooks": own}
    except Exception:
        raise ProfileError("invalid_hook_inventory") from None


def _validate_document(data):
    try:
        if not isinstance(data, dict) or set(data) != _FIELDS or type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError()
        base = bootstrap_profile(data["runtime"], data["surface"], data["host_version"])
        if base is None:
            raise ValueError()
        for key in ("project_hash", "source_project_hash", "binary_identity", "implementation_sha256", "hook_digest"):
            if not isinstance(data[key], str) or not _HASH.fullmatch(data[key]):
                raise ValueError()
        created, expires = data["created_at"], data["expires_at"]
        if any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 for x in (created, expires)) or not 0 < expires-created <= 86400:
            raise ValueError()
        catalog = CatalogRegistry.from_json(_json(data["catalog"]))
        VersionSnapshot.capture("profile-schema-1", DEFAULT_CONFIG, catalog)
        if not catalog.records:
            raise ValueError()
        for record in catalog.records:
            if (record.runtime != base.spawn.runtime or record.surface != data["surface"] or record.host_version != data["host_version"]
                    or record.tool_name not in base.spawn.tools or record.mapping_status != "verified"
                    or record.availability_source == "unknown" or record.effort_field != ("reasoning_effort" if data["runtime"] == "codex" else "effort")):
                raise ValueError()
            if data["runtime"] == "codex" and record.runtime_model_id != f"gpt-{record.target_version}-{record.family}":
                raise ValueError()
        return base, catalog
    except Exception:
        raise ProfileError("invalid_capability_profile") from None


def build_profile_document(*, runtime, surface, version, project, binary, profile_path, catalog, hooks, now=None):
    now = time.time() if now is None else now
    project_hash, source_hash = _project(project)
    result = analyze_hooks(hooks, runtime=runtime, surface=surface, project=project, binary=binary, profile_path=profile_path)
    # Persist no free-form source evidence or raw hook command/arguments.
    entries = json.loads(catalog.to_json())
    for entry in entries["entries"]:
        entry["mapping_evidence"] = "evidence_sha256:" + _hash(entry["mapping_evidence"])
    document = {"schema_version": 1, "runtime": runtime, "surface": surface, "host_version": version,
        "project_hash": project_hash, "source_project_hash": source_hash, "binary_identity": binary_identity(binary),
        "implementation_sha256": implementation_digest(), "hook_digest": result["hook_digest"],
        "created_at": now, "expires_at": now+86400, "catalog": entries}
    _validate_document(document)
    return document, result


def read_profile(path):
    fd = rootfd = None
    try:
        path = Path(os.path.abspath(path))
        store = PrivateStateStore(path.parent)
        rootfd = store._open_root(create=False)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=rootfd)
        info = store._check_file(fd)
        if info.st_size > MAX_PROFILE_BYTES:
            raise ValueError()
        with os.fdopen(fd, "rb") as file:
            fd = None
            raw = file.read(MAX_PROFILE_BYTES+1)
        if len(raw) > MAX_PROFILE_BYTES:
            raise ValueError()
        data = json.loads(raw, object_pairs_hook=_unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        _validate_document(data)
        return data
    except Exception:
        raise ProfileError("profile_unavailable_or_unsafe") from None
    finally:
        if fd is not None:
            os.close(fd)
        if rootfd is not None:
            os.close(rootfd)


def write_profile(path, document):
    _validate_document(document)
    raw = _json(document).encode("ascii")
    if len(raw) > MAX_PROFILE_BYTES:
        raise ProfileError("profile_size_limit")
    path = Path(os.path.abspath(path))
    rootfd = fd = None
    temporary = ".profile-" + secrets.token_hex(16)
    try:
        # Refuse to replace a key/config/unrelated or unsafe existing file.
        if path.exists() or path.is_symlink():
            read_profile(path)
        rootfd = PrivateStateStore(path.parent)._open_root()
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=rootfd)
        with os.fdopen(fd, "wb") as file:
            fd = None
            file.write(raw);file.flush();os.fsync(file.fileno())
        os.replace(temporary, path.name, src_dir_fd=rootfd, dst_dir_fd=rootfd)
        os.fsync(rootfd)
    except Exception:
        raise ProfileError("profile_write_failed") from None
    finally:
        if fd is not None:
            os.close(fd)
        if rootfd is not None:
            try:
                os.unlink(temporary, dir_fd=rootfd)
            except FileNotFoundError:
                pass
            os.close(rootfd)


def load_capability_profile(path, *, runtime, surface, version, project, binary, hooks=None, now=None):
    data = read_profile(path)
    base, catalog = _validate_document(data)
    now = time.time() if now is None else now
    expected = (runtime, surface, version, *_project(project), binary_identity(binary), implementation_digest())
    actual = tuple(data[k] for k in ("runtime", "surface", "host_version", "project_hash", "source_project_hash", "binary_identity", "implementation_sha256"))
    if expected != actual or not data["created_at"] <= now < data["expires_at"]:
        raise ProfileError("profile_stale_or_scope_mismatch")
    if runtime != "codex":
        raise ProfileError("hook_inventory_unverified_for_runtime")
    if hooks is None:
        hooks = read_codex_hooks(binary, base.spawn, os.path.abspath(project))
    result = analyze_hooks(hooks, runtime=runtime, surface=surface, project=project, binary=binary, profile_path=path)
    if result["hook_digest"] != data["hook_digest"]:
        raise ProfileError("hook_inventory_changed")
    # Only this exact CLI/permission mode has measured native rewrite evidence.
    modes = frozenset({"bypassPermissions"}) if result["safe"] and (runtime, surface, version) == ("codex", "cli", "0.163.0") else frozenset()
    return replace(base, catalog=catalog, conflicts_checked=result["safe"], safe_rewrite_permission_modes=modes)

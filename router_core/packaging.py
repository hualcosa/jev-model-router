"""Build self-contained project-bound native plugins; never install or enable.

Only allowlisted source code and explicit non-secret path bindings are copied.
Provider consent, credentials, native trust and host configuration are external.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat

from .state import PrivateStateStore

ROOT = Path(__file__).resolve().parents[1]
NAME = "intelligent-agent-router"
VERSION = "0.1.0"
MAX_BYTES = 2_097_152


class PackageError(ValueError):
    """Sanitized error code, no paths or input content."""


def _absolute(value):
    value = os.fspath(value)
    if (not isinstance(value, str) or not os.path.isabs(value) or len(value) > 4096
            or any(c in value for c in "\0\n\r") or "${" in value):
        # Native plugin interpolation runs even inside shell single quotes.
        # Refuse its placeholder syntax in ALL caller-supplied path bytes.
        raise PackageError("invalid_path_binding")
    return os.path.abspath(value)


@dataclass(frozen=True)
class Bindings:
    project: str
    python: str
    runtime_binary: str
    global_config: str
    state_dir: str
    capability_profile: str | None = None
    key_file: str | None = None
    surface: str = "cli"
    global_scope: bool = False

    def __post_init__(self):
        if type(self.global_scope) is not bool:
            raise PackageError("invalid_scope")
        for field in ("project", "python", "runtime_binary", "global_config", "state_dir"):
            object.__setattr__(self, field, _absolute(getattr(self, field)))
        if self.capability_profile is not None:
            object.__setattr__(self, "capability_profile", _absolute(self.capability_profile))
        if self.key_file is not None:
            object.__setattr__(self, "key_file", _absolute(self.key_file))
        if self.surface not in ("cli", "desktop"):
            raise PackageError("invalid_surface")
        if not Path(self.project).is_dir():
            raise PackageError("project_unavailable")
        for executable in (self.python, self.runtime_binary):
            info = os.stat(executable)
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or not os.access(executable, os.X_OK):
                raise PackageError("unsafe_executable")

    def arguments(self, *, hook, runtime="codex"):
        args = (["--scope", "global"] if self.global_scope else ["--project", self.project]) + ["--runtime-binary", self.runtime_binary,
                "--surface", self.surface, "--global-config", self.global_config,
                "--state-dir", self.state_dir]
        if self.capability_profile is not None:
            args += ["--capability-profile", self.capability_profile]
        if hook:
            args += ["--runtime", runtime]
        if self.key_file is not None:
            args += ["--key-file", self.key_file]
        return args


def _json(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False)+"\n").encode("ascii")


def _write(rootfd, relative, raw):
    """Descriptor-anchored exclusive writes, including every generated directory."""
    parts = relative.split("/")
    if any(part in ("", ".", "..") for part in parts) or relative.startswith("/"):
        raise PackageError("invalid_package_path")
    fd = os.dup(rootfd)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, 0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise PackageError("unsafe_package_directory")
        filefd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        with os.fdopen(filefd, "wb") as file:
            file.write(raw)
            file.flush(); os.fsync(file.fileno())
        os.fsync(fd)
    finally:
        os.close(fd)


def _build_package(output, bindings, *, source_root=ROOT, runtime):
    """Create a NEW private local marketplace folder; existing paths are refused.

    A failed build may leave an incomplete private artifact for inspection. No
    host command, provider, config, key or target project file is accessed.
    """
    rootfd = None
    try:
        if not isinstance(bindings, Bindings):
            raise PackageError("invalid_bindings")
        if runtime == "codex" and bindings.capability_profile is None:
            raise PackageError("codex_capability_profile_required")
        if runtime == "claude" and bindings.capability_profile is not None:
            raise PackageError("claude_capability_profile_not_supported")
        output = Path(_absolute(output))
        # Canonicalize only the build parent, never native project spelling.
        output = output.parent.resolve(strict=True)/output.name
        source_root = Path(source_root).resolve(strict=True)
        files = {}
        sources = [(p, "router_core/"+p.name) for p in sorted((source_root/"router_core").glob("*.py"))]
        sources += [(source_root/"scripts"/name, "scripts/"+name)
                    for name in ("router_hook.py", "router_mcp.py", "router_cli.py")]
        if runtime == "claude" and bindings.global_scope:
            sources += [(source_root/"scripts/router_claude_mod.py", "scripts/router_claude_mod.py")]
            sources += [(p, "hooks/"+p.name) for p in sorted((source_root/"router_core/claude_mod").glob("*.js"))]
        if not sources or not any(relative == "router_core/__init__.py" for _, relative in sources):
            raise PackageError("source_unavailable")
        total = 0
        for path, relative in sources:
            # No caches, specs, tests, key files or symlinked source can enter.
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as file:
                info = os.fstat(file.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                    raise PackageError("unsafe_source")
                raw = file.read(MAX_BYTES+1)
            total += len(raw)
            if total > MAX_BYTES:
                raise PackageError("package_size_limit")
            files["plugins/"+NAME+"/"+relative] = raw
        prefix = "plugins/"+NAME+"/"
        # Unbraced spelling is essential: Codex literally replaces ${KEY} with
        # path bytes BEFORE shell parsing. Shell environment expansion inside
        # double quotes instead keeps quotes/$()/backticks in the value literal.
        # All explicit bindings use shlex literal quoting.
        events = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
                  "SubagentStart", "SubagentStop", "PostCompact", "SessionEnd")
        if runtime == "codex":
            command = (shlex.quote(bindings.python) + ' "$PLUGIN_ROOT/scripts/router_hook.py" '
                       + shlex.join(bindings.arguments(hook=True)))
            hooks = {event: [{"hooks": [{"type": "command", "command": command,
                                    "timeout": 3 if event == "SessionEnd" else 30 if bindings.global_scope and event == "SessionStart" else 10}],
                          **({"matcher": "^(?:collaborationspawn_agent|collaboration\\.spawn_agent|spawn_agent)$"}
                             if event in ("PreToolUse", "PostToolUse") else {})}] for event in events}
        else:
            events += ("Stop", "PostModelSwitch", "TaskCreated", "TaskCompleted")
            # Current Claude supports native exec form: substitution stays in
            # argv, so no shell can reinterpret plugin-path or binding bytes.
            hooks = {event: [{"hooks": [{"type": "command", "command": bindings.python,
                "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/router_hook.py",
                         *bindings.arguments(hook=True, runtime="claude")],
                "onFailure": "continue", "timeout": 3 if event == "SessionEnd" else 10}],
                **({"matcher": "^(Agent|Task)$"} if event in ("PreToolUse", "PostToolUse") else {})}]
                for event in events}
        hook_document = {"hooks": hooks}
        if runtime == "claude" and bindings.global_scope:
            # Classic command hooks remain advisory/observational. Only the
            # native post-batch mod may propose automatic worker changes.
            hook_document["modules"] = ["./register.js"]
            files[prefix+"hooks/bindings.js"] = ("export const bindings = " + json.dumps({
                "python": bindings.python, "args": bindings.arguments(hook=True, runtime="claude")
            }, ensure_ascii=True) + ";\n").encode("ascii")
        files[prefix+"hooks/hooks.json"] = _json(hook_document)
        if runtime == "codex":
            files[prefix+".mcp.json"] = _json({"mcpServers": {"intelligent_router": {
            "command": bindings.python, "args": ["${PLUGIN_ROOT}/scripts/router_mcp.py", *bindings.arguments(hook=False)],
            "env": {"PYTHONNOUSERSITE": "1"}}}})
            manifest_path = prefix+".codex-plugin/plugin.json"
            files[manifest_path] = _json({"name": NAME, "version": VERSION,
            "description": "Task-aware root advice and native worker routing; disabled until separate configuration and hook trust.",
            "hooks": "./hooks/hooks.json", "mcpServers": "./.mcp.json", "requires_local_executor": True})
        else:
            manifest_path = prefix+".claude-plugin/plugin.json"
            files[manifest_path] = _json({"name": NAME, "version": VERSION,
                "description": "Task-aware advisory without root autoswitch; separately gated native worker routing.",
                "author": {"name": "Intelligent Agent Router contributors"}, "license": "MIT"})
        scope = hashlib.sha256((("global" if bindings.global_scope else bindings.project)+"\0"+bindings.surface).encode()).hexdigest()[:12]
        marketplace = "intelligent-router-local-"+scope
        if runtime == "codex":
            files[".agents/plugins/marketplace.json"] = _json({"name": marketplace, "plugins": [{"name": NAME,
            "source": {"source": "local", "path": "./plugins/"+NAME}}]})
        else:
            files[".claude-plugin/marketplace.json"] = _json({"name": marketplace,
                "owner": {"name": "Intelligent Agent Router contributors"},
                "plugins": [{"name": NAME, "source": "./plugins/"+NAME}]})
        # The code license travels with the self-contained source distribution.
        license_path = source_root/"LICENSE"
        if license_path.is_symlink() or not license_path.is_file():
            raise PackageError("license_unavailable")
        license_raw = license_path.read_bytes()
        if len(license_raw) > 65536:
            raise PackageError("license_size_limit")
        files[prefix+"LICENSE"] = license_raw
        # Native caches are version-addressed. Changing code OR path bindings
        # must produce a new version, never silently reuse an older cache copy.
        payload = {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(files.items())
                   if name != manifest_path}
        version = VERSION+"+"+hashlib.sha256(_json(payload)).hexdigest()[:12]
        manifest = json.loads(files[manifest_path])
        manifest["version"] = version
        files[manifest_path] = _json(manifest)
        files["BUILD.json"] = _json({"schema_version": 1, "plugin": NAME, "version": version,
            "marketplace": marketplace, "runtime": runtime, "surface": bindings.surface, "routing_enabled": False,
            "host_config_changed": False, "credentials_included": False,
            "sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(files.items())}})
        # Exclusive root creation refuses ordinary files, existing folders and
        # dangling symlinks. Never replace an existing user artifact.
        os.mkdir(output, 0o700)
        rootfd = PrivateStateStore(output)._open_root(create=False)
        for name, raw in sorted(files.items(), key=lambda item: item[0] == "BUILD.json"):
            _write(rootfd, name, raw)
        current = os.stat(output, follow_symlinks=False)
        original = os.fstat(rootfd)
        if (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino):
            raise PackageError("package_path_changed")
        return {"status": "built_not_installed", "plugin": NAME, "marketplace": marketplace, "version": version,
                "file_count": len(files), "runtime": runtime, "surface": bindings.surface, "routing_enabled": False,
                "credentials_included": False, "trust_granted": False}
    except PackageError:
        raise
    except Exception:
        raise PackageError("package_build_failed") from None
    finally:
        if rootfd is not None:
            os.close(rootfd)


def build_codex_package(output, bindings, *, source_root=ROOT):
    return _build_package(output, bindings, source_root=source_root, runtime="codex")


def build_claude_package(output, bindings, *, source_root=ROOT):
    return _build_package(output, bindings, source_root=source_root, runtime="claude")

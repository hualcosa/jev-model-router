"""Read-only public Codex app-server model/list inventory; never starts a turn."""
from datetime import datetime, timezone
import json
import os
import re
import selectors
import signal
import subprocess
import time

from .catalog import CapabilityRecord, CatalogRegistry
from .classifier import _unique
from .config import TARGET_VERSIONS
from .spawn import CapabilityProfile

_MODEL = re.compile(r"gpt-(\d+(?:\.\d+)*)-(luna|terra|sol|astra)\Z")
_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max", "ultra"})
MAX_MODELS = 256
MAX_BYTES = 1_048_576


class InventoryError(ValueError):
    """Contains only a bounded diagnostic code."""


def normalize_codex_models(entries, profile, *, verified_at):
    """Exact versioned slugs only; aliases/display labels never prove a mapping."""
    if (not isinstance(profile, CapabilityProfile) or profile.runtime.value != "codex" or
            profile.surface != "cli" or not isinstance(entries, list) or len(entries) > MAX_MODELS):
        raise InventoryError("invalid_inventory_scope")
    records, seen, advertised = [], set(), []
    try:
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError()
            model = entry.get("model")
            if (not isinstance(model, str) or len(model) > 256 or
                    entry.get("id") != model or model in seen):
                raise ValueError()
            seen.add(model)
            match = _MODEL.fullmatch(model)
            if match is None:
                continue
            version, family = match.groups()
            advertised.append(model)
            # Explicitly expose historical/different generations as excluded,
            # never silently map Terra5.6 to requested Terra6.
            if TARGET_VERSIONS["codex"].get(family) != version:
                continue
            raw_efforts = entry.get("supportedReasoningEfforts")
            if not isinstance(raw_efforts, list) or not 1 <= len(raw_efforts) <= len(_EFFORTS):
                raise ValueError()
            efforts = []
            for option in raw_efforts:
                effort = option.get("reasoningEffort") if isinstance(option, dict) else None
                if not isinstance(effort, str) or effort not in _EFFORTS or effort in efforts:
                    raise ValueError()
                efforts.append(effort)
            if entry.get("defaultReasoningEffort") not in efforts:
                raise ValueError()
            for tool, schema in profile.tools.items():
                if ("model" not in schema.argument_fields or "reasoning_effort" not in schema.argument_fields
                        or "string" not in schema.field_types["model"]
                        or "string" not in schema.field_types["reasoning_effort"]):
                    continue
                records.append(CapabilityRecord("codex", "cli", profile.host_version, family, version,
                    model, tool, "model", "reasoning_effort", tuple(sorted(efforts)), "verified",
                    "Official model/list exact slug and advertised effort options; spawn fields separately verified",
                    "official_app_server_model_list", verified_at, "user_assumption"))
        registry = CatalogRegistry(tuple(records))
        present = {(r.family, r.target_version) for r in registry.records}
        missing = [f"{family}:{version}" for family, version in TARGET_VERSIONS["codex"].items()
                   if (family, version) not in present]
        return {"catalog": json.loads(registry.to_json()), "advertised_versioned_models": sorted(advertised),
                "missing_desired_targets": sorted(missing), "entitlement": "user_assumption_not_inference_verified",
                "source": "official_app_server_model_list", "inference_calls": 0}
    except Exception:
        raise InventoryError("invalid_model_list") from None


class _MetadataSession:
    METHODS = frozenset({"initialize", "model/list", "hooks/list"})

    def __init__(self, binary, profile, deadline_seconds):
        if not isinstance(binary, str) or not os.path.isabs(binary) or type(deadline_seconds) not in (int, float) or not 0 < deadline_seconds <= 30:
            raise InventoryError("invalid_inventory_input")
        self.binary, self.profile = binary, profile
        self.deadline_seconds = deadline_seconds
        self.process = None
        self.selector = selectors.DefaultSelector()
        self.buffer, self.total, self.ident = b"", 0, 0

    def __enter__(self):
        try:
            self.end = time.monotonic() + self.deadline_seconds
            version = subprocess.run([self.binary, "--version"], stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=min(2, self.deadline_seconds), check=True).stdout
            if not isinstance(self.profile, CapabilityProfile) or version.strip() != ("codex-cli " + self.profile.host_version).encode("ascii"):
                raise InventoryError("host_version_mismatch")
            self.process = subprocess.Popen([self.binary, "app-server", "--listen", "stdio://"], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
            self.call("initialize", {"clientInfo": {"name": "intelligent_router_inventory", "version": "1.0.0"}})
            self._send({"method": "initialized"})
            return self
        except InventoryError:
            self.__exit__(None, None, None)
            raise
        except Exception:
            self.__exit__(None, None, None)
            raise InventoryError("inventory_unavailable") from None

    def _send(self, message):
        self.process.stdin.write((json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8"))
        self.process.stdin.flush()

    def call(self, method, params):
        if method not in self.METHODS:
            raise InventoryError("metadata_method_forbidden")
        self.ident += 1
        self._send({"id": self.ident, "method": method, "params": params})
        while time.monotonic() < self.end:
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                response = json.loads(line, object_pairs_hook=_unique,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                if not isinstance(response, dict):
                    raise ValueError()
                if type(response.get("id")) is int and response["id"] == self.ident:
                    if "error" in response or not isinstance(response.get("result"), dict):
                        raise InventoryError("inventory_request_failed")
                    return response["result"]
            if self.selector.select(max(0, self.end - time.monotonic())):
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise InventoryError("inventory_eof")
                self.total += len(chunk)
                if self.total > MAX_BYTES:
                    raise InventoryError("inventory_size_limit")
                self.buffer += chunk
        raise InventoryError("inventory_timeout")

    def __exit__(self, *_):
        self.selector.close()
        if self.process is not None:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.communicate()


def discover_codex_models(binary, profile, *, deadline_seconds=10):
    """Bounded public model inventory, no thread/turn/inference/private API."""
    try:
        with _MetadataSession(binary, profile, deadline_seconds) as session:
            entries, cursor, cursors = [], None, set()
            for _ in range(8):
                page = session.call("model/list", {"limit": 100, "includeHidden": True, **({"cursor": cursor} if cursor else {})})
                if not isinstance(page.get("data"), list):
                    raise ValueError()
                entries.extend(page["data"])
                if len(entries) > MAX_MODELS:
                    raise InventoryError("inventory_size_limit")
                cursor = page.get("nextCursor")
                if cursor is None:
                    break
                if not isinstance(cursor, str) or not cursor or len(cursor) > 4096 or cursor in cursors:
                    raise ValueError()
                cursors.add(cursor)
            else:
                raise InventoryError("inventory_page_limit")
            return normalize_codex_models(entries, profile, verified_at=datetime.now(timezone.utc).isoformat())
    except InventoryError:
        raise
    except Exception:
        raise InventoryError("inventory_unavailable") from None


def read_codex_hooks(binary, profile, project, *, deadline_seconds=5):
    """Return ephemeral public hook metadata, not arbitrary config/transcripts.

    Callers must not log raw commands (they may contain private user data).
    """
    try:
        if not isinstance(project, str) or not os.path.isabs(project) or len(project) > 4096:
            raise ValueError()
        with _MetadataSession(binary, profile, deadline_seconds) as session:
            response = session.call("hooks/list", {"cwds": [project]})
        data = response.get("data")
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise ValueError()
        row = data[0]
        if row.get("cwd") != project or not isinstance(row.get("hooks"), list) or len(row["hooks"]) > 1024:
            raise ValueError()
        if row.get("warnings") != [] or row.get("errors") != []:
            raise InventoryError("hook_inventory_incomplete")
        return row["hooks"]
    except InventoryError:
        raise
    except Exception:
        raise InventoryError("hook_inventory_unavailable") from None

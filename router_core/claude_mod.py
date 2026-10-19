"""Proposal bridge for the native post-classic Claude middleware.

Unlike a command PreToolUse hook, the caller has already awaited the actual
classic batch. It preserves that batch's permissions and applies only routing
fields. Never use this profile as command-hook conflict authority.
"""
import argparse
import hashlib
from dataclasses import replace
import json
import os
from pathlib import Path
import sys

from .classifier import JevClient
from .credentials import load_private_key
from .global_scope import scoped_config, state_path
from .hook import runtime_version
from .native import NativeAdapter, bootstrap_profile
from .state import PrivateStateStore

NATIVE_SHA256 = "d2da3b003dc08b88b7230469014fe3e1dc6fe94bc8f648e89b34175d30269370"
COMPANION_SHA256 = "d352a405996fd6a8f6bbdfdd3ca774c692467195793ef8a572f6a551bce1e756"


def verify_host(binary, companion):
    """Exact measured host and audited, non-routing Ponytail mod sources."""
    if hashlib.sha256(Path(binary).read_bytes()).hexdigest() != NATIVE_SHA256:
        return False
    root = Path(companion)
    if root.is_symlink() or not root.is_dir():
        return False
    files = {}
    paths = [root/".claude-plugin/plugin.json", root/"hooks/claude-band.json",
             root/"hooks/claude-codex-hooks.json", *(root/"hooks/band").glob("*")]
    for path in sorted(paths):
        if path.is_file():
            if path.is_symlink() or path.stat().st_size > 2_097_152:
                return False
            files[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == COMPANION_SHA256


def proposal(event, config, store, classify, *, project, version):
    if config.mode != "auto_workers" or version != "2.1.303":
        return None
    if not isinstance(event, dict) or event.get("hook_event_name") != "PreToolUse":
        return None
    # The mod alone owns native permission merging; the bridge never emits
    # allow/ask/deny. 'default' is an internal assessment label, not a native
    # permission-mode assertion or request to change the session mode.
    event = {**event, "permission_mode": "default"}
    profile = replace(bootstrap_profile("claude", "cli", version),
        conflicts_checked=True, safe_rewrite_permission_modes=frozenset({"default"}))
    output = NativeAdapter(profile, config, store, classify, project_id=project).handle(event)
    updated = (output or {}).get("hookSpecificOutput", {}).get("updatedInput")
    if not isinstance(updated, dict):
        return None
    original = event.get("tool_input")
    if {k: v for k, v in updated.items() if k not in ("model", "effort")} != original:
        return None
    return {k: updated[k] for k in ("model", "effort") if k in updated}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=("claude",), required=True)
    parser.add_argument("--surface", choices=("cli", "desktop"), required=True)
    parser.add_argument("--runtime-binary", required=True)
    parser.add_argument("--global-config", type=Path, required=True)
    parser.add_argument("--scope", choices=("global",), required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--key-file", type=Path)
    args = parser.parse_args()
    if os.environ.get("ROUTER_DISABLE", "").lower() in ("1", "true", "yes"):
        return 0
    try:
        if args.surface != "cli":
            return 0
        project = Path.cwd().resolve()
        raw = sys.stdin.buffer.read(262145)
        if len(raw) > 262144:
            return 0
        def unique(pairs):
            out = {}
            for key, value in pairs:
                if key in out:
                    raise ValueError("duplicate")
                out[key] = value
            return out
        event = json.loads(raw, object_pairs_hook=unique)
        config = scoped_config(args.global_config, project)
        if config.mode == "disabled":
            return 0
        if event.get("operation") == "verify":
            print(json.dumps({"verified": verify_host(args.runtime_binary, event.get("companion", ""))}))
            return 0
        if config.mode != "auto_workers":
            return 0
        if not isinstance(event, dict) or event.get("cwd") != str(project):
            return 0
        def classify(description):
            key = load_private_key(args.key_file) if args.key_file else os.environ.get("TYPESAFE_API_KEY")
            return JevClient(api_key=key, deadline_ms=config.classification.deadline_ms).classify(description)
        output = proposal(event, config, PrivateStateStore(state_path(args.state_dir, Path.cwd())),
                          classify, project=str(project), version=runtime_version(args.runtime_binary))
        if output is not None:
            print(json.dumps(output, separators=(",", ":"), allow_nan=False))
    except Exception:
        pass
    return 0

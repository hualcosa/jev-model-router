"""Bounded official command-hook entrypoint, disabled by default."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from .classifier import JevClient
from .config import load_config
from .credentials import load_private_key
from .native import NativeAdapter, bootstrap_profile
from .state import PrivateStateStore
from .profiles import load_capability_profile


def runtime_version(binary):
    if not isinstance(binary, str) or not os.path.isabs(binary):
        return None
    try:
        result = subprocess.run([binary, "--version"], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=1.5, check=True)
        match = re.search(rb"\b(\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?)\b", result.stdout[:1024])
        return match.group(1).decode("ascii") if match else None
    except (OSError, subprocess.SubprocessError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=("claude", "codex"), required=True)
    parser.add_argument("--surface", choices=("cli", "desktop"), required=True)
    parser.add_argument("--runtime-binary", required=True)
    parser.add_argument("--global-config", type=Path,
                        default=Path.home()/".config/intelligent-agent-router/config.json")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--scope", choices=("global",))
    parser.add_argument("--state-dir", type=Path,
                        default=Path.home()/".local/state/intelligent-agent-router")
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--capability-profile", type=Path)
    args = parser.parse_args()
    if args.scope != "global" and args.project is None or args.scope == "global" and args.project is not None:
        parser.error("choose explicit project or global scope")
    # The emergency switch must avoid even config/state/credential reads.
    if os.environ.get("ROUTER_DISABLE", "").lower() in ("1", "true", "yes"):
        return 0
    try:
        source_project = Path.cwd() if args.scope == "global" else args.project
        project = source_project.resolve()
        if args.scope == "global":
            from .global_scope import scoped_config
            config = scoped_config(args.global_config, project)
        else:
            config = load_config(args.global_config, project/".intelligent-agent-router.json")
        if config.mode == "disabled":
            return 0
        raw = sys.stdin.buffer.read(262145)
        if len(raw) > 262144:
            return 0
        # Reject duplicate top-level/native argument keys rather than silently
        # selecting the last pin or tool field.
        def unique(pairs):
            out = {}
            for key, value in pairs:
                if key in out:
                    raise ValueError()
                out[key] = value
            return out
        event = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(event, dict) or not isinstance(event.get("cwd"), str) or os.path.realpath(event["cwd"]) != str(project):
            return 0
        version = runtime_version(args.runtime_binary)
        state_dir = args.state_dir
        if args.scope == "global":
            from .global_scope import state_path, codex_profile
            state_dir = state_path(state_dir, source_project)
        if args.scope == "global" and args.runtime == "codex":
            profile = codex_profile(args.capability_profile, project=source_project, binary=args.runtime_binary,
                surface=args.surface, version=version, refresh=event.get("hook_event_name") == "SessionStart")
        else:
            profile = (load_capability_profile(args.capability_profile, runtime=args.runtime, surface=args.surface,
                    version=version, project=source_project, binary=args.runtime_binary)
                   if args.capability_profile else bootstrap_profile(args.runtime, args.surface, version))
        if profile is None:
            return 0
        # Keys are resolved lazily only after the adapter/policy consent gates.
        def classify(description):
            key = load_private_key(args.key_file) if args.key_file else os.environ.get("TYPESAFE_API_KEY")
            return JevClient(api_key=key, deadline_ms=config.classification.deadline_ms).classify(description)
        store = PrivateStateStore(state_dir)
        output = NativeAdapter(profile, config, store, classify, project_id=str(project)).handle(event)
        if output is not None:
            print(json.dumps(output, allow_nan=False, separators=(",", ":")))
    except Exception:
        # Fail-open command hook, no exception text on stderr/stdout.
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

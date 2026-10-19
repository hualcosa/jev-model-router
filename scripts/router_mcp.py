#!/usr/bin/env python3
"""Local stdio MCP preparation facade; uses the official Codex host unchanged."""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from router_core.classifier import JevClient
from router_core.config import load_config
from router_core.credentials import load_private_key
from router_core.hook import runtime_version
from router_core.mcp import MCPServer
from router_core.native import NativeAdapter, bootstrap_profile
from router_core.preparation import PreparationService
from router_core.state import PrivateStateStore
from router_core.profiles import load_capability_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--scope", choices=("global",))
    parser.add_argument("--runtime-binary", required=True)
    parser.add_argument("--surface", choices=("cli", "desktop"), default="cli")
    parser.add_argument("--global-config", type=Path, default=Path.home()/".config/intelligent-agent-router/config.json")
    parser.add_argument("--state-dir", type=Path, default=Path.home()/".local/state/intelligent-agent-router")
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--capability-profile", type=Path)
    args = parser.parse_args()
    if args.scope != "global" and args.project is None or args.scope == "global" and args.project is not None:
        parser.error("choose explicit project or global scope")
    source_project = Path.cwd() if args.scope == "global" else args.project
    project = source_project.resolve()
    state_dir = args.state_dir
    if args.scope == "global":
        from router_core.global_scope import state_path, codex_profile
        state_dir = state_path(state_dir, source_project)
    def build_adapter():
        # Long-lived stdio servers must not retain revoked consent or stale
        # rewrite authority until restart. Refresh at each prepare_task call.
        try:
            if os.environ.get("ROUTER_DISABLE", "").lower() in ("1", "true", "yes"):
                return None
            if args.scope == "global":
                from router_core.global_scope import scoped_config
                config = scoped_config(args.global_config, project)
            else:
                config = load_config(args.global_config, project/".intelligent-agent-router.json")
            if config.mode == "disabled":
                return None
            version = runtime_version(args.runtime_binary)
            if args.scope == "global":
                profile = codex_profile(args.capability_profile, project=source_project, binary=args.runtime_binary,
                    surface=args.surface, version=version)
            else:
                profile = (load_capability_profile(args.capability_profile, runtime="codex", surface=args.surface,
                    version=version, project=source_project, binary=args.runtime_binary) if args.capability_profile
                    else bootstrap_profile("codex", args.surface, version))
            if profile is None:
                return None
            def classify(description):
                key = load_private_key(args.key_file) if args.key_file else os.environ.get("TYPESAFE_API_KEY")
                return JevClient(api_key=key, deadline_ms=config.classification.deadline_ms).classify(description)
            return NativeAdapter(profile, config, PrivateStateStore(state_dir), classify, project_id=str(project))
        except Exception:
            return None
    MCPServer(PreparationService(None, refresh=build_adapter)).serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())

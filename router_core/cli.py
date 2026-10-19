"""Read-only local payload preview and explicitly requested route preflight."""
import argparse
import json
import os
from pathlib import Path
import sys

from .classifier import JevClient
from .config import load_config
from .contracts import EventKind, TaskEnvelope
from .credentials import load_private_key
from .hook import runtime_version
from .native import bootstrap_profile
from .policy import POLICY_VERSION, PolicyScope, assess
from .privacy import MAX_INPUT_BYTES, preview_task_description
from .snapshots import VersionSnapshot
from .inventory import discover_codex_models, read_codex_hooks
from .catalog import CatalogRegistry
from .explain import explain_history, scope_hash_for, ExplainError
from .state import PrivateStateStore
from .profiles import build_profile_document, write_profile, load_capability_profile, binary_identity


def preflight(task_text, *, runtime, profile, config, classify):
    """No state, spawning, config mutation or task execution. Injectable I/O."""
    if profile is None or profile.spawn.runtime.value != runtime:
        return {"status": "defer", "reason_code": "runtime_unverified"}
    tool = next(iter(profile.spawn.tools))
    envelope = TaskEnvelope(runtime, EventKind.PREFLIGHT, "explicit-preflight",
                            "explicit-preflight", task_text, False)
    decision = assess(envelope, classify, profile.catalog, config,
        PolicyScope(profile.spawn.surface, profile.spawn.host_version, tool))
    return {"status": "assessed", "decision": decision.to_dict(),
            "snapshot": VersionSnapshot.capture(POLICY_VERSION, config, profile.catalog).to_dict(),
            "task_executed": False, "host_config_changed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preview", "preflight", "inventory", "diagnose", "explain"))
    parser.add_argument("--send", action="store_true", help="request one Jev assessment; existing consent still required")
    parser.add_argument("--runtime", choices=("claude", "codex"))
    parser.add_argument("--surface", choices=("cli", "desktop"), default="cli")
    parser.add_argument("--runtime-binary")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--global-config", type=Path, default=Path.home()/".config/intelligent-agent-router/config.json")
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--capability-profile", type=Path)
    parser.add_argument("--write-profile", action="store_true", help="diagnose only: atomically write private profile, never enable routing")
    parser.add_argument("--state-dir", type=Path, default=Path.home()/".local/state/intelligent-agent-router")
    parser.add_argument("--scope-hash", help="explain: exact retained scope hash; never inferred from other sessions")
    parser.add_argument("--session-id", help="explain: explicit alternative with --runtime and --project; not printed")
    parser.add_argument("--row-id", help="explain: one exact retained row inside the selected scope")
    def explain_limit(value):
        if not value.isascii() or not value.isdecimal() or len(value) > 2 or not 1 <= int(value) <= 50:
            raise argparse.ArgumentTypeError("limit must be an integer from 1 to 50")
        return int(value)
    parser.add_argument("--limit", type=explain_limit, default=20, help="explain: last 1..50 retained rows (default 20)")
    args = parser.parse_args(argv)
    project_explicit = args.project is not None
    if args.project is None:
        args.project = Path.cwd()
    if args.command == "explain":
        if args.send or args.write_profile or args.runtime_binary or args.key_file or args.capability_profile:
            parser.error("explain is offline and does not accept execution, key or profile flags")
        if ((args.scope_hash is None and (args.session_id is None or not args.runtime or not project_explicit))
                or (args.scope_hash is not None and (args.session_id is not None or project_explicit))):
            parser.error("explain requires --scope-hash alone, or explicit --runtime --session-id --project")
        try:
            selected_scope = args.scope_hash if args.scope_hash is not None else scope_hash_for(args.runtime, args.project, args.session_id)
            output = explain_history(PrivateStateStore(args.state_dir), selected_scope,
                runtime=args.runtime, surface=args.surface, row_id=args.row_id, limit=args.limit)
            print(json.dumps(output, allow_nan=False, separators=(",", ":")))
            return 0
        except Exception as error:
            reason = error.code if isinstance(error, ExplainError) else "explain_unavailable"
            print(json.dumps({"status":"error", "reason_code":reason, "external_calls":0, "state_modified":False}))
            return 2
    if args.write_profile and args.command != "diagnose":
        parser.error("--write-profile is only supported by diagnose")
    if args.command == "diagnose":
        if args.send or args.runtime != "codex" or not args.runtime_binary or not args.capability_profile:
            parser.error("diagnose requires --runtime codex --runtime-binary --capability-profile and never accepts --send")
        try:
            identity = binary_identity(args.runtime_binary)
            version = runtime_version(args.runtime_binary)
            base = bootstrap_profile("codex", args.surface, version)
            if base is None:
                raise ValueError()
            inventory = discover_codex_models(args.runtime_binary, base.spawn)
            hooks = read_codex_hooks(args.runtime_binary, base.spawn, os.path.abspath(args.project))
            document, analysis = build_profile_document(runtime="codex", surface=args.surface, version=version,
                project=args.project, binary=args.runtime_binary, profile_path=args.capability_profile,
                catalog=CatalogRegistry.from_json(json.dumps(inventory["catalog"])), hooks=hooks)
            if identity != document["binary_identity"]:
                raise ValueError()
            if args.write_profile:
                write_profile(args.capability_profile, document)
            output = {"status": "ready_for_measured_permission_mode" if analysis["safe"] else "advisory_only",
                      "runtime": "codex", "surface": args.surface, "host_version": version,
                      "reason_codes": analysis["reason_codes"], "hook_digest": analysis["hook_digest"],
                      "profile_written": args.write_profile, "routing_enabled": False,
                      "supported_auto_permission_modes": ["bypassPermissions"] if analysis["safe"] else [],
                      "missing_desired_targets": inventory["missing_desired_targets"], "inference_calls": 0,
                      "notice": "No model calls, key access, trust changes or host configuration changes. Profile is not an installation or opt-in."}
            print(json.dumps(output, allow_nan=False, separators=(",", ":")))
            return 0
        except Exception:
            print('{"status":"error","reason_code":"diagnostic_unavailable"}')
            return 2
    if args.command == "inventory":
        if args.send or args.runtime != "codex" or not args.runtime_binary:
            parser.error("inventory requires --runtime codex --runtime-binary and never accepts --send")
        try:
            profile = bootstrap_profile("codex", args.surface, runtime_version(args.runtime_binary))
            if profile is None:
                raise ValueError()
            output = discover_codex_models(args.runtime_binary, profile.spawn)
            print(json.dumps(output, allow_nan=False, separators=(",", ":")))
            return 0
        except Exception:
            print('{"status":"error","reason_code":"inventory_unavailable"}')
            return 2
    if args.command == "preview" and args.send:
        parser.error("preview never sends; use preflight --send")
    if args.command == "preflight" and args.send and (not args.runtime or not args.runtime_binary):
        parser.error("preflight --send requires --runtime and --runtime-binary")
    try:
        # Preview has no config/runtime/key reads and cannot grant consent.
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError()
        text = raw.decode("utf-8")
        description = preview_task_description(text)
        if not args.send:
            output = {"status": "local_preview", "external_calls": 0,
                      "payload": description.provider_state(), "metadata": description.safe_metadata(),
                      "notice": "Local only. Best-effort redaction; inspect for private content. No outbound consent granted."}
        elif os.environ.get("ROUTER_DISABLE", "").lower() in ("1", "true", "yes"):
            output = {"status": "defer", "reason_code": "emergency_disabled"}
        else:
            project = args.project.resolve()
            config = load_config(args.global_config, project/".intelligent-agent-router.json")
            version = runtime_version(args.runtime_binary) if config.mode != "disabled" else None
            profile = (None if config.mode == "disabled" else load_capability_profile(args.capability_profile,
                runtime=args.runtime, surface=args.surface, version=version, project=args.project,
                binary=args.runtime_binary) if args.capability_profile else bootstrap_profile(args.runtime, args.surface, version))
            def classify(payload):
                key = load_private_key(args.key_file) if args.key_file else os.environ.get("TYPESAFE_API_KEY")
                return JevClient(api_key=key, deadline_ms=config.classification.deadline_ms).classify(payload)
            output = preflight(text, runtime=args.runtime, profile=profile, config=config, classify=classify)
        print(json.dumps(output, allow_nan=False, separators=(",", ":")))
        return 0
    except Exception:
        print('{"status":"error","reason_code":"invalid_preflight_input_or_config"}')
        return 2


if __name__ == "__main__":
    sys.exit(main())

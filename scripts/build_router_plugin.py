#!/usr/bin/env python3
"""Build a private native local-marketplace artifact; never install or activate."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from router_core.packaging import Bindings, PackageError, build_codex_package, build_claude_package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--runtime", choices=("codex", "claude"), default="codex")
    for name in ("project", "python", "runtime-binary", "global-config", "state-dir"):
        parser.add_argument("--"+name, required=True)
    parser.add_argument("--capability-profile", help="Required for Codex; not supported for Claude yet")
    parser.add_argument("--surface", choices=("cli", "desktop"), default="cli")
    parser.add_argument("--global-scope", action="store_true", help="Use host cwd with isolated per-project state/profiles")
    parser.add_argument("--key-file")
    args = vars(parser.parse_args())
    output = args.pop("output")
    runtime = args.pop("runtime")
    try:
        build = build_codex_package if runtime == "codex" else build_claude_package
        result = build(output, Bindings(**args))
        print(json.dumps(result, separators=(",", ":")))
        return 0
    except PackageError as error:
        print(json.dumps({"status": "error", "reason_code": str(error)}))
        return 2
    except Exception:
        print('{"status":"error","reason_code":"invalid_package_bindings"}')
        return 2


if __name__ == "__main__":
    sys.exit(main())

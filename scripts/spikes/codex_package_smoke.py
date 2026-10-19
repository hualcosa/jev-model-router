"""Explicit no-inference install/disable/uninstall test in a fresh CODEX_HOME.

Never uses user authentication or grants hook trust. Keeps private artifacts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from router_core.packaging import Bindings, NAME, build_codex_package

_COMMAND_SHAPE_CHECK = '''import sys,json
sys.path.insert(0,sys.argv[1])
from router_core.inventory import read_codex_hooks
from router_core.native import bootstrap_profile
from router_core.profiles import _own_command
cache,project,binary,profile_path=sys.argv[1:]
hooks=read_codex_hooks(binary,bootstrap_profile("codex","cli","0.163.0").spawn,project)
spawn=[h for h in hooks if h.get("eventName")=="preToolUse"]
recognized=len(spawn)==1 and _own_command(spawn[0].get("command"),runtime="codex",surface="cli",
 project=project,binary=binary,profile_path=profile_path,source=spawn[0].get("source"),
 source_path=spawn[0].get("sourcePath"),plugin_id=spawn[0].get("pluginId"))
print(json.dumps({"spawn_command_recognized":bool(recognized),"hook_count":len(hooks),"hook_events":sorted(h.get("eventName") for h in hooks),
 "all_hooks_untrusted":all(h.get("trustStatus")=="untrusted" for h in hooks),
 "unbraced_root_token_preserved":len(spawn)==1 and '"$PLUGIN_ROOT/scripts/router_hook.py"' in spawn[0].get("command","")}))
'''


def config_snapshot(root):
    """Hash only configuration files, never auth/key files or their contents in output."""
    result = {}
    for name in ("config.toml", "hooks.json"):
        try:
            fd = os.open(root/name, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        except FileNotFoundError:
            result[name] = None
            continue
        with os.fdopen(fd, "rb") as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1_048_576:
                raise ValueError("baseline_config_unavailable")
            raw = file.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError("baseline_config_unavailable")
        result[name] = hashlib.sha256(raw).hexdigest()
    return result


def run(binary="/opt/homebrew/bin/codex", python=sys.executable):
    user_home = Path(os.environ.get("CODEX_HOME", str(Path.home()/".codex"))).resolve()
    before_user = config_snapshot(user_home)
    fixture = Path(tempfile.mkdtemp(prefix="router-package-native-")).resolve()
    project, home, private = (fixture/name for name in ("project", "codex-home", "private"))
    for path in (project, home, private):
        path.mkdir(mode=0o700)
    package = fixture/"marketplace"
    bindings = Bindings(str(project), python, binary, str(private/"config.json"),
                        str(private/"state"), str(private/"profile.json"))
    build = build_codex_package(package, bindings)
    selector = NAME+"@"+build["marketplace"]
    env = {**os.environ, "CODEX_HOME": str(home)}
    for name in ("TYPESAFE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        env.pop(name, None)
    commands = []
    def cli(arguments):
        proc = subprocess.run([binary, *arguments], env=env, cwd=project,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30, check=False)
        # All CLI commands are known local package operations, never exec/turn.
        record = {"arguments": arguments, "exit_code": proc.returncode,
                  "stdout": proc.stdout, "stderr": proc.stderr}
        commands.append(record)
        if proc.returncode != 0:
            raise ValueError("native_package_command_failed")
        return json.loads(proc.stdout) if "--json" in arguments else {}
    def installed():
        rows = cli(["plugin", "list", "--marketplace", build["marketplace"], "--json"])["installed"]
        return [r for r in rows if r.get("pluginId") == selector]
    try:
        cli(["plugin", "marketplace", "add", str(package), "--json"])
        addition = cli(["plugin", "add", selector, "--json"])
        cache = Path(addition["installedPath"])
        if home not in cache.parents or not (cache/"router_core/native.py").is_file():
            raise ValueError("installed_cache_missing")
        active = installed()
        if len(active) != 1 or active[0].get("enabled") is not True:
            raise ValueError("native_install_not_enabled")
        # Read-only doctor from the INSTALLED copy proves no checkout import.
        # No --write-profile, provider call or trust mutation is requested.
        args = [python, str(cache/"scripts/router_cli.py"), "diagnose", "--runtime", "codex",
                "--runtime-binary", binary, "--project", str(project),
                "--capability-profile", str(private/"profile.json")]
        doctor = subprocess.run(args, env=env, cwd=project, capture_output=True, text=True, timeout=20)
        diagnostic = json.loads(doctor.stdout)
        if doctor.returncode or diagnostic.get("status") != "advisory_only" or diagnostic.get("profile_written") is not False:
            raise ValueError("installed_doctor_failed")
        if diagnostic.get("reason_codes") != ["matching_hook_needs_review", "router_hook_missing_or_duplicated"]:
            raise ValueError("unexpected_trust_or_own_hook_detection")
        shape_proc = subprocess.run([python, "-c", _COMMAND_SHAPE_CHECK, str(cache), str(project), binary,
                                     str(private/"profile.json")], env=env, cwd=project,
                                    capture_output=True, text=True, timeout=15)
        shape = json.loads(shape_proc.stdout)
        if shape_proc.returncode or shape != {"spawn_command_recognized": True, "hook_count": 8,
                "hook_events": sorted(["sessionStart", "userPromptSubmit", "preToolUse", "postToolUse",
                                       "subagentStart", "subagentStop", "postCompact", "sessionEnd"]),
                "all_hooks_untrusted": True, "unbraced_root_token_preserved": True}:
            raise ValueError("installed_command_shape_unverified")
        # Supported native config toggle, only in the disposable home. Preserve
        # all other generated configuration; do not modify user's config.
        config = home/"config.toml"
        raw = config.read_text()
        table = '[plugins.'+json.dumps(selector)+']'
        if raw.count(table) != 1:
            raise ValueError("unexpected_disposable_config")
        before, table_body = raw.split(table, 1)
        if table_body.count("enabled = true") != 1:
            raise ValueError("unexpected_disposable_config")
        config.write_text(before+table+table_body.replace("enabled = true", "enabled = false", 1))
        disabled = installed()
        if len(disabled) != 1 or disabled[0].get("enabled") is not False:
            raise ValueError("native_disable_failed")
        cli(["plugin", "remove", selector])
        removed = not installed()
        if not removed or cache.exists():
            raise ValueError("native_uninstall_failed")
        cli(["plugin", "marketplace", "remove", build["marketplace"]])
        registrations = cli(["plugin", "marketplace", "list", "--json"])
        if build["marketplace"] in json.dumps(registrations):
            raise ValueError("marketplace_removal_failed")
        # Never delete private router state/keys as part of native uninstall.
        if (private/"profile.json").exists() or (private/"state").exists() or (private/"config.json").exists():
            raise ValueError("unexpected_routing_side_effect")
        result = {"status": "passed", "runtime": "codex", "surface": "cli", "inference_calls": 0,
            "external_jev_calls": 0, "host_version": diagnostic["host_version"], "package_version": addition["version"],
            "native_local_install": True, "native_disable": True, "native_uninstall": True, "native_marketplace_removed": True,
            "installed_copy_doctor": diagnostic, "installed_command_shape": shape,
            "hook_trust_granted": False, "user_home_config_changed": False,
            "cache_removed": True, "private_fixture": str(fixture),
            "not_proven": ["native hook execution after trust", "production provider-to-worker chain", "desktop installation", "packaged TUI execution"]}
    except Exception as error:
        codes = {"native_package_command_failed", "installed_cache_missing", "native_install_not_enabled",
                 "installed_doctor_failed", "unexpected_trust_or_own_hook_detection", "unexpected_disposable_config",
                 "native_disable_failed", "native_uninstall_failed", "unexpected_routing_side_effect",
                 "installed_command_shape_unverified", "marketplace_removal_failed"}
        result = {"status": "unverified", "reason_code": str(error) if type(error) is ValueError and str(error) in codes else "package_smoke_failed",
                  "private_fixture": str(fixture), "inference_calls": 0, "hook_trust_granted": False}
    unchanged = before_user == config_snapshot(user_home)
    result["user_home_config_changed"] = not unchanged
    result["user_config_files_verified"] = ["config.toml", "hooks.json"]
    if not unchanged:
        result.update(status="unverified", reason_code="user_config_changed_during_test")
    # Artifacts contain only this disposable fixture's package command results.
    fd = os.open(fixture/"commands.json", os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        json.dump(commands, file, indent=2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-isolated", action="store_true")
    parser.add_argument("--binary", default="/opt/homebrew/bin/codex")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.run_isolated:
        parser.error("--run-isolated is required; changes only a disposable CODEX_HOME")
    result = run(args.binary, args.python)
    rendered = json.dumps(result, indent=2)+"\n"
    if args.output:
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())

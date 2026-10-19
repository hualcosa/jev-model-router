"""Bounded, offline Docker execution for Python benchmark candidates.

Candidates are never imported or evaluated by the host. This is defense in depth
for synthetic benchmark code, not a hardened multi-tenant security sandbox or an
adversarially tamper-proof judge: candidate and trusted tests share a Python
interpreter. Use only a previously inspected, cached official Python image ID.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import tempfile
import time
import uuid

MAX_INPUT_BYTES = 64 * 1024
MAX_OUTPUT_BYTES = 64 * 1024
_IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MARKER = "__BENCHMARK_RESULT__="


def _kill_group(proc):
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        if proc.poll() is None:
            proc.kill()

# This program is trusted; only solution.py is supplied by a model. -I excludes
# the script directory, so explicitly add the single readonly bundle directory.
_GRADER = '''import json, sys, unittest
sys.path.insert(0, "/bundle")
import trusted_tests
suite = unittest.defaultTestLoader.loadTestsFromModule(trusted_tests)
result = unittest.TextTestRunner(verbosity=1).run(suite)
print("__BENCHMARK_RESULT__=" + json.dumps({
    "tests_run": result.testsRun,
    "failures": len(result.failures),
    "errors": len(result.errors),
    "skipped": len(result.skipped),
}), flush=True)
sys.exit(0 if result.wasSuccessful() and result.testsRun > 0 else 1)
'''


def _capture(command: list[str], timeout: float, limit: int = MAX_OUTPUT_BYTES, *, cwd=None, env=None):
    """Drain both pipes without communicate()'s unbounded allocation."""
    started = time.monotonic()
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.DEVNULL, start_new_session=True, cwd=cwd, env=env)
    chunks = {"stdout": bytearray(), "stderr": bytearray()}
    total = 0
    reason = None
    try:
        with selectors.DefaultSelector() as selector:
            for label, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, label)
            while selector.get_map():
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    reason = "timeout"
                    break
                for key, _ in selector.select(min(remaining, 0.1)):
                    data = os.read(key.fd, min(8192, limit - total + 1))
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(data)
                    chunks[key.data].extend(data[:max(0, limit - sum(map(len, chunks.values())))])
                    if total > limit:
                        reason = "output_limit"
                        break
                if reason:
                    break
        if reason:
            _kill_group(proc)  # Docker cleanup additionally kills its container.
        try:
            proc.wait(timeout=max(0.01, timeout - (time.monotonic() - started)))
        except subprocess.TimeoutExpired:
            reason = reason or "timeout"
            _kill_group(proc)
            proc.wait(timeout=2)
        return proc.returncode, bytes(chunks["stdout"]), bytes(chunks["stderr"]), reason, min(total, limit)
    finally:
        if proc.poll() is None:
            _kill_group(proc)
            proc.wait(timeout=2)
        proc.stdout.close()
        proc.stderr.close()


def _cleanup(docker: str, name: str, label: str) -> bool:
    """Force removal even after an abruptly exiting client; verify daemon state."""
    try:
        _capture([docker, "rm", "--force", name], 5)
        code, out, _, reason, _ = _capture(
            [docker, "ps", "--all", "--quiet", "--filter", f"label={label}"], 5)
        return code == 0 and reason is None and not out.strip()
    except (OSError, subprocess.SubprocessError):
        return False


def _counts(stdout: bytes) -> dict | None:
    records = [line[len(_MARKER):] for line in stdout.decode("utf-8", "replace").splitlines()
               if line.startswith(_MARKER)]
    if len(records) != 1:
        return None
    try:
        record = json.loads(records[0])
        keys = {"tests_run", "failures", "errors", "skipped"}
        if not isinstance(record, dict) or set(record) != keys:
            return None
        if any(type(v) is not int or not 0 <= v <= 100000 for v in record.values()):
            return None
        if sum(record[k] for k in ("failures", "errors", "skipped")) > record["tests_run"]:
            return None
        return record
    except (ValueError, TypeError):
        return None


def grade_python(source: str, tests_source: str, *, image: str,
                 docker_binary: str = "docker", timeout_seconds: float = 10) -> dict:
    """Execute source plus trusted unittest tests with fixed Docker restrictions.

    ``tests_source`` should import ``solution`` and define unittest.TestCase
    classes (no unittest.main call). Only sanitized metrics leave this API.
    Invalid API inputs raise ValueError before any Docker operation. Caller must
    provision/inspect the official Python image; this function never pulls.
    """
    if not isinstance(image, str) or not _IMAGE.fullmatch(image):
        raise ValueError("image must be an immutable sha256 image ID")
    if not isinstance(docker_binary, str) or not docker_binary or docker_binary.startswith("-"):
        raise ValueError("docker_binary must identify a Docker executable")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (float, int)) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 60:
        raise ValueError("timeout_seconds must be finite and between 0 and 60")
    for text in (source, tests_source):
        if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValueError("source and tests_source must each be strings of at most 64KiB")

    started = time.monotonic()
    token = uuid.uuid4().hex
    name = f"router-code-grader-{token}"
    label = f"router-code-grader.task={token}"
    result = {"passed": False, "status": "runner_error", "exit_code": None,
              "tests_run": None, "failures": None, "errors": None, "skipped": None,
              "output_bytes": 0, "cleanup_verified": False}
    with tempfile.TemporaryDirectory(prefix="router-grader-") as directory:
        bundle = Path(directory)
        # TemporaryDirectory starts 0700: allow the container's uid 65534 read
        # access to only this freshly created bundle, never home/project paths.
        bundle.chmod(0o755)
        for filename, contents in (("solution.py", source), ("trusted_tests.py", tests_source), ("grader.py", _GRADER)):
            path = bundle / filename
            path.write_text(contents, encoding="utf-8")
            path.chmod(0o444)
        command = [docker_binary, "run", "--pull=never", "--log-driver", "none", "--name", name,
                   "--label", label, "--network", "none", "--read-only",
                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                   "--user", "65534:65534", "--pids-limit", "32", "--memory", "128m",
                   "--memory-swap", "128m", "--cpus", "1", "--stop-timeout", "1",
                   "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
                   "--mount", f"type=bind,source={bundle},target=/bundle,readonly",
                   "--workdir", "/tmp", "--entrypoint", "python", image,
                   "-I", "-B", "/bundle/grader.py"]
        try:
            code, stdout, _, reason, total = _capture(command, float(timeout_seconds))
            result.update(exit_code=code, output_bytes=total)
            if reason:
                result["status"] = reason
            else:
                counts = _counts(stdout)
                if counts:
                    result.update(counts)
                passed = bool(counts and counts["tests_run"] > 0 and code == 0
                              and counts["failures"] == counts["errors"] == 0
                              and counts["skipped"] == 0)
                result.update(passed=passed, status="passed" if passed else
                              "failed" if counts else "invalid_result" if code in (0, 1) else "runner_error")
        except (OSError, subprocess.SubprocessError):
            pass  # Never expose daemon errors, candidate output, or host paths.
        finally:
            result["cleanup_verified"] = _cleanup(docker_binary, name, label)
            if not result["cleanup_verified"]:
                result.update(passed=False, status="cleanup_error")
    result["duration_seconds"] = round(time.monotonic() - started, 6)
    return result


def _synthetic_smoke(image: str) -> dict:
    tests = "import unittest, solution\nclass Check(unittest.TestCase):\n def test_value(self): self.assertEqual(solution.answer(), 42)\n"
    candidates = {
        "positive": "def answer(): return 42\n",
        "wrong_answer": "def answer(): return 0\n",
        "network_denied": "import socket\ndef answer():\n try: socket.create_connection(('1.1.1.1', 53), timeout=.5)\n except OSError: return 42\n return 0\n",
        "filesystem_denied": "def answer():\n for path in ['/bundle/solution.py', '/etc/grader-proof']:\n  try:\n   with open(path, 'w') as handle: handle.write('bad')\n  except OSError: continue\n  return 0\n return 42\n",
        "infinite": "while True: pass\n",
        "flood": "import os\nwhile True: os.write(1, b'x' * 8192)\n",
    }
    return {name: grade_python(source, tests, image=image, timeout_seconds=2)
            for name, source in candidates.items()}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-synthetic", action="store_true", required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    outcomes = _synthetic_smoke(args.image)
    print(json.dumps(outcomes, indent=2, sort_keys=True))
    expected = {"positive": "passed", "wrong_answer": "failed", "network_denied": "passed",
                "filesystem_denied": "passed", "infinite": "timeout", "flood": "output_limit"}
    raise SystemExit(0 if all(outcomes[k]["status"] == v and outcomes[k]["cleanup_verified"]
                             for k, v in expected.items()) else 1)

"""Optional official Jev SDK with a hard enclosing wall-clock deadline.

One isolated process per classification bounds SDK retries, import time, DNS and
transport time together. No shell, no key in argv, no stderr or raw responses in
errors/telemetry. Consent/minimization is required before constructing a request.
This module never classifies a raw TaskEnvelope or full transcript.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from .contracts import ProviderResult, ProviderStatus
from .normalizer import normalize_response
from .privacy import MAX_OUTPUT_BYTES, TaskDescription


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_provider_field")
        result[key] = value
    return result


class JevClient:
    def __init__(self, *, api_key=None, deadline_ms=2500, worker_command=None):
        if type(deadline_ms) is not int or not 50 <= deadline_ms <= 2500:
            raise ValueError("invalid_classifier_deadline")
        if api_key is not None and (not isinstance(api_key, str) or not api_key or
                                    len(api_key) > 8192 or any(not 33 <= ord(c) <= 126 for c in api_key)):
            raise ValueError("invalid_api_key")
        self._key = api_key
        self.deadline_ms = deadline_ms
        # Dependency injection is trusted application/test code only. It must
        # never be a config field or derived from tool/project arguments.
        self._command = tuple(worker_command) if worker_command is not None else (
            # Isolated mode excludes the script directory, cwd and PYTHONPATH.
            # Otherwise sibling packaging.py shadows the SDK's packaging.version
            # dependency when this worker is launched by its absolute filename.
            sys.executable, "-I", str(Path(__file__).with_name("_jev_worker.py").resolve()))

    def classify(self, description):
        def failure(reason, unavailable=False):
            return ProviderResult(ProviderStatus.UNAVAILABLE if unavailable else ProviderStatus.FAILURE,
                                  provider="typesafe_jev", reason_code=reason)
        if not isinstance(description, TaskDescription):
            return failure("unprepared_task")
        try:
            if not description.text.strip() or len(description.text.encode("utf-8")) > MAX_OUTPUT_BYTES:
                return failure("invalid_task_description")
        except (AttributeError, UnicodeError):
            return failure("invalid_task_description")
        key = self._key
        if not key:
            return failure("missing_key", unavailable=True)
        start = time.monotonic()
        # The worker protocol is kept below a pipe buffer and contains only the
        # minimized description, the private key and the transport time limit.
        payload = json.dumps({"api_key": key, "task_summary": description.text,
                              "timeout_seconds": self.deadline_ms / 1000}, ensure_ascii=False).encode("utf-8")
        process = None
        try:
            process = subprocess.Popen(self._command, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       start_new_session=True)
            remaining = self.deadline_ms / 1000 - (time.monotonic() - start)
            if remaining <= 0:
                raise subprocess.TimeoutExpired(self._command, self.deadline_ms / 1000)
            output, _ = process.communicate(payload, timeout=remaining)
            if time.monotonic() - start > self.deadline_ms / 1000:
                return failure("timeout")
            if process.returncode != 0 or len(output) > 16_384:
                return failure("provider_process_failure")
            raw = json.loads(output, object_pairs_hook=_unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if isinstance(raw, dict) and set(raw) == {"error"}:
                reason = raw["error"]
                allowed = {"sdk_unavailable", "sdk_version_mismatch", "provider_failure", "invalid_provider_schema"}
                if not isinstance(reason, str) or reason not in allowed:
                    return failure("invalid_provider_schema")
                return failure(reason, unavailable=reason.startswith("sdk_"))
            return ProviderResult(ProviderStatus.SUCCESS, normalize_response(raw), provider="typesafe_jev")
        except subprocess.TimeoutExpired:
            return failure("timeout")
        except (OSError, ValueError, TypeError, UnicodeError):
            return failure("invalid_provider_schema")
        finally:
            if process is not None:
                # A timed-out SDK can have subprocesses/threads; stop the whole
                # process group before returning. No background classifier survives.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate()

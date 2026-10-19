"""Bounded task descriptions; no I/O, logging, credentials or provider calls.

Redaction is a best-effort minimizer, NOT a guarantee that arbitrary private
content is safe to disclose. Consent is required even after redaction. Only
exact, explicitly registered synthetic fixtures qualify for synthetic consent;
callers cannot turn a real task into one by supplying a boolean flag.
"""
from dataclasses import dataclass, field
from enum import Enum
import re


class Consent(str, Enum):
    NONE = "none"
    SYNTHETIC = "synthetic"
    REAL_TASKS = "real_tasks"


class PrivacyError(ValueError):
    """Contains a bounded reason code only, never input text."""


SYNTHETIC_SMOKE = "List the names of three imaginary files: alpha.py, beta.py, gamma.py."
DEFAULT_SYNTHETIC_TASKS = frozenset({SYNTHETIC_SMOKE})
MAX_INPUT_BYTES = 100_000
MAX_OUTPUT_BYTES = 8_192
REDACTED = "[REDACTED]"

# Bounded input size is checked before regex processing. Each rule is linear
# over that input (no nested ambiguous repetition). Order matters: remove a
# complete credential before truncation, never transmit its surviving prefix.
_RULES = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)"),
    re.compile(r"(?i)\b(?:authorization\s*[:=]\s*)?(?:bearer|basic)\s+[A-Za-z0-9_./+~=-]+"),
    re.compile(r"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9-]{8,}|(?:AKIA|ASIA)[A-Z0-9]{16})\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]{0,31}://[^\s/@:]+:[^\s/@]+@"),
    # Consume escape pairs atomically: an escaped quote in JSON/shell-like
    # values must not terminate redaction and expose the credential suffix.
    # Unterminated quoted values (including a dangling backslash) redact to EOF.
    # Alternatives are disjoint by leading byte, including the unquoted branch.
    re.compile(r'''(?i)["']?\b(?:[a-z0-9_]{0,64}(?:api[_-]?key|access[_-]?key|secret|password|passwd|token|credential)[a-z0-9_]{0,64})["']?\s*[:=]\s*(?:"(?:\\[\s\S]|[^"\\])*(?:"|\\?\Z)|'(?:\\[\s\S]|[^'\\])*(?:'|\\?\Z)|[^"'\s,;&}\]\r\n]+)'''),
    re.compile(r"(?im)^\s*(?:export\s+)?(?:DATABASE_URL|DSN)\s*=.*$"),
)


@dataclass(frozen=True)
class TaskDescription:
    # Avoid accidental plaintext leakage in repr/trace logging.
    text: str = field(repr=False)
    redactions: int
    truncated: bool
    omitted_code: bool

    def provider_state(self):
        """Explicit outbound payload; never attach a transcript or envelope."""
        return {"task_summary": self.text}

    def safe_metadata(self):
        return {"payload_bytes": len(self.text.encode("utf-8")),
                "redactions": self.redactions, "truncated": self.truncated,
                "omitted_code": self.omitted_code}


def build_task_description(task_text, *, consent=Consent.NONE,
                           synthetic_tasks=DEFAULT_SYNTHETIC_TASKS,
                           max_bytes=MAX_OUTPUT_BYTES):
    """Authorize, minimize and redact an in-memory single task description.

    The synthetic fixture set must be supplied by trusted application code,
    never project/user tool arguments. Non-consenting callers receive no preview
    payload. Raw serialized TaskEnvelope/transcript input is not accepted.
    """
    if not isinstance(consent, Consent):
        raise PrivacyError("invalid_consent")
    if consent is Consent.NONE:
        raise PrivacyError("no_consent")
    if consent is Consent.SYNTHETIC:
        if not isinstance(synthetic_tasks, frozenset) or not isinstance(task_text, str) or task_text not in synthetic_tasks:
            raise PrivacyError("synthetic_fixture_not_authorized")
    return preview_task_description(task_text, max_bytes=max_bytes)


def preview_task_description(task_text, *, max_bytes=MAX_OUTPUT_BYTES):
    """Minimize for LOCAL inspection only; does not grant outbound consent.

    This pure function performs no network or credential access. A preview is
    best-effort redacted, not guaranteed free of private content. Sending still
    requires build_task_description and the policy's separate consent gates.
    """
    if not isinstance(task_text, str):
        raise PrivacyError("invalid_task_text")
    if type(max_bytes) is not int or not 64 <= max_bytes <= MAX_OUTPUT_BYTES:
        raise PrivacyError("invalid_payload_limit")
    try:
        size = len(task_text.encode("utf-8"))
    except UnicodeError:
        raise PrivacyError("invalid_task_encoding") from None
    if size > MAX_INPUT_BYTES:
        raise PrivacyError("task_too_large")
    text = task_text.replace("\r\n", "\n")
    # Drop control characters, but preserve words and line separation.
    text = "".join(c for c in text if c in "\n\t" or (ord(c) >= 32 and ord(c) != 127))
    count = 0
    for rule in _RULES:
        text, n = rule.subn(REDACTED, text)
        count += n
    # Code and incidental transcripts are not needed for requirement estimates.
    # An unterminated fence drops the rest, rather than leaking a partial block.
    text, code_count = re.subn(r"(?m)^\s*(`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:\n\s*\1\s*(?=\n|$)|\Z)",
                               "\n[code block omitted]\n", text)
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not text:
        raise PrivacyError("empty_task_description")
    encoded = text.encode("utf-8")
    truncated = len(encoded) > max_bytes
    if truncated:
        marker = "\n[truncated]"
        text = encoded[:max_bytes-len(marker)].decode("utf-8", errors="ignore") + marker
    return TaskDescription(text, count, truncated, bool(code_count))

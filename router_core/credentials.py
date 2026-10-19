"""Private credential reader. No shell evaluation or diagnostic secret values."""
import os
import stat


def load_private_key(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "r") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                (os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077))):
            raise ValueError("invalid_credential_file")
        raw = stream.read(16385)
    lines = [line.strip() for line in raw.splitlines() if line.strip() and not line.startswith("#")]
    if len(raw) > 16384 or len(lines) != 1 or not lines[0].startswith("TYPESAFE_API_KEY="):
        raise ValueError("invalid_credential_file")
    value = lines[0].split("=", 1)[1]
    if not value or len(value) > 8192 or any(not 33 <= ord(c) <= 126 for c in value) or value in ("COLE_SUA_KEY_AQUI", "YOUR_API_KEY"):
        raise ValueError("invalid_credential_file")
    return value

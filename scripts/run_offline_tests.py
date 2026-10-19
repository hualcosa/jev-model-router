#!/usr/bin/env python3
"""Run offline contracts; the SDK CI cell must never silently skip coverage.

No credentials or native runtime binaries are needed. The SDK tests use a mock
transport, not a Jev endpoint. Dependency installation is a separate CI step.
"""
import argparse
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SDK_VERSION = "0.7.5"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-sdk", action="store_true")
    args = parser.parse_args(argv)
    if args.require_sdk:
        try:
            if version("typesafe-sdk") != SDK_VERSION:
                raise ValueError()
            import typesafe_sdk  # noqa: F401 — prove importability, not just metadata
            import httpx2  # noqa: F401
        except (PackageNotFoundError, ImportError, ValueError):
            print("offline_sdk_dependency_unavailable_or_wrong_version", file=sys.stderr)
            return 2
    sys.path.insert(0, str(ROOT))
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if args.require_sdk and result.skipped:
        print("offline_required_suite_skipped_tests", file=sys.stderr)
        return 1
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

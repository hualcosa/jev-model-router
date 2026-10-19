#!/usr/bin/env python3
"""Installed-copy native Claude proposal bridge; never import the project cwd."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from router_core.claude_mod import main

if __name__ == "__main__":
    sys.exit(main())

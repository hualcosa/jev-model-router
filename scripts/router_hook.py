#!/usr/bin/env python3
"""Absolute-path launcher; never import a user's cwd as the router package."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from router_core.hook import main

if __name__ == "__main__":
    sys.exit(main())

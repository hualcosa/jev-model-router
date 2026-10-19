#!/usr/bin/env python3
"""Absolute-path launcher; does not import code from the caller's project."""
import sys
# Offline commands must not modify even a relocated package via import caches.
sys.dont_write_bytecode = True
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from router_core.cli import main

if __name__ == "__main__":
    sys.exit(main())

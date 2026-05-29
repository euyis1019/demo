#!/usr/bin/env python3
"""Shim — forwards to scripts/tests/test_m0.py (dev_logs/38 Phase R1)."""

import sys

from agent_world.hbm_demo.scripts.tests.test_m0 import main

if __name__ == "__main__":
    sys.exit(main())

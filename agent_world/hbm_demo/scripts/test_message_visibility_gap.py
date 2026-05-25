#!/usr/bin/env python3
"""F12 message visibility — legacy entrypoint delegates to test_f12_visibility.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "agent_world" / "hbm_demo" / "scripts" / "test_f12_visibility.py"

if __name__ == "__main__":
    raise SystemExit(
        subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=str(ROOT)).returncode
    )

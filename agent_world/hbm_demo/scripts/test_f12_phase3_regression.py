#!/usr/bin/env python3
"""F12 Phase 3 regression — frontend worldSync + full stack (dev_logs/32 §七 Phase 3)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HBM_DIR = ROOT / "agent_world" / "hbm_demo"
WEB_DIR = HBM_DIR / "web"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestFailure(Exception):
    pass


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def _apply_env() -> dict[str, str]:
    from agent_world.hbm_demo.scripts.test_m0_acceptance import apply_hbm_demo_env

    return apply_hbm_demo_env(dict(os.environ))


def _run_script(name: str, rel_path: str) -> None:
    script = HBM_DIR / "scripts" / rel_path
    if not script.is_file():
        raise TestFailure(f"missing {script}")
    proc = subprocess.run(
        [sys.executable, "-B", str(script)],
        cwd=str(ROOT),
        env=_apply_env(),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise TestFailure(
            f"{name} failed (exit {proc.returncode}):\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    ok(f"{name} passed")


def test_world_sync_ts() -> None:
    section("F12 Phase 3 worldSync TypeScript unit tests")
    script = WEB_DIR / "scripts" / "test_world_sync.ts"
    if not script.is_file():
        raise TestFailure(f"missing {script}")
    proc = subprocess.run(
        ["npx", "--yes", "tsx", str(script)],
        cwd=str(WEB_DIR),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise TestFailure(
            proc.stdout + proc.stderr or "worldSync ts tests failed"
        )
    ok("worldSync.ts unit tests passed")


def test_phase3_static() -> None:
    section("F12 Phase 3 static frontend checks")
    from agent_world.hbm_demo.scripts.test_m0_acceptance import (
        test_f12_phase3_world_stage,
    )

    test_f12_phase3_world_stage()


def main() -> int:
    print("F12 Phase 3 regression (dev_logs/32)")
    failures: list[str] = []

    for name, rel in (
        ("F12 Phase 1 persistence", "test_f12_phase1_persistence.py"),
        ("F12 Phase 2 world delta unit", "test_f12_world_delta.py"),
    ):
        try:
            _run_script(name, rel)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{rel}: {exc}")
            print(f"  ✗ {exc}")

    try:
        test_phase3_static()
    except Exception as exc:  # noqa: BLE001
        failures.append(f"phase3_static: {exc}")
        print(f"  ✗ {exc}")

    try:
        test_world_sync_ts()
    except Exception as exc:  # noqa: BLE001
        failures.append(f"world_sync_ts: {exc}")
        print(f"  ✗ {exc}")

    section("npm run build")
    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(WEB_DIR),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise TestFailure(proc.stdout + proc.stderr or "npm run build failed")
        ok("npm run build passed")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"npm_build: {exc}")
        print(f"  ✗ {exc}")

    section("M0 acceptance (E2E + F12 API + npm build in suite)")
    try:
        _run_script("test_m0_acceptance", "test_m0_acceptance.py")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"test_m0_acceptance: {exc}")
        print(f"  ✗ {exc}")

    if failures:
        print(f"\nFAILED ({len(failures)}):")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("\nALL F12 PHASE 3 REGRESSION TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

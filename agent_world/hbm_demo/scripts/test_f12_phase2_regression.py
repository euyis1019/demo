#!/usr/bin/env python3
"""F12 Phase 2 regression — unit + acceptance + E2E (dev_logs/32 §七 Phase 2)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HBM_DIR = ROOT / "agent_world" / "hbm_demo"

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


def test_import_graph() -> None:
    section("F12 Phase 2 import graph")
    from agent_world.hbm_demo.features.f12_world_sync.delta import (
        build_completed_payload,
        build_world_delta,
        empty_delta,
    )
    from agent_world.hbm_demo.features.f12_world_sync.handler import get_world_snapshot
    from agent_world.hbm_demo.features.f11_live_turn_sync.delta import (
        build_turn_delta,
        empty_delta as f11_empty,
    )
    import agent_world.hbm_demo.game_service as gs

    ed = empty_delta(0)
    if "room_f2f" not in ed:
        raise TestFailure("empty_delta missing room_f2f")
    if gs.get_world_snapshot is not get_world_snapshot:
        raise TestFailure("game_service.get_world_snapshot shim broken")
    if f11_empty(1)["through_tick"] != 1:
        raise TestFailure("F11 empty_delta delegate broken")
    if build_turn_delta is build_world_delta:
        raise TestFailure("F11 should wrap F12 build_world_delta")
    ok("F12/F11/F03 import graph healthy")


def main() -> int:
    print("F12 Phase 2 regression (dev_logs/32)")
    failures: list[str] = []

    unit_scripts = (
        ("F12 Phase 1 persistence", "test_f12_phase1_persistence.py"),
        ("F12 Phase 2 world delta unit", "test_f12_world_delta.py"),
    )

    try:
        test_import_graph()
    except Exception as exc:  # noqa: BLE001
        failures.append(f"import_graph: {exc}")
        print(f"  ✗ {exc}")

    for name, rel in unit_scripts:
        try:
            _run_script(name, rel)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{rel}: {exc}")
            print(f"  ✗ {exc}")

    section("M0 acceptance (includes F12 E2E + npm build)")
    try:
        _run_script("test_m0_acceptance", "test_m0_acceptance.py")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"test_m0_acceptance: {exc}")
        print(f"  ✗ {exc}")

    section("F12 Phase 3 frontend build smoke")
    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(HBM_DIR / "web"),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise TestFailure(proc.stdout + proc.stderr or "npm run build failed")
        ok("npm run build passed")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"npm_build: {exc}")
        print(f"  ✗ {exc}")

    if failures:
        print(f"\nFAILED ({len(failures)}):")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("\nALL F12 PHASE 2 REGRESSION TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

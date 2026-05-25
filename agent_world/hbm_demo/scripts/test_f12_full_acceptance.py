#!/usr/bin/env python3
"""F12 full-plan acceptance — Phases 1–4 automated regression (dev_logs/32)."""

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


def _run_py(name: str, rel: str) -> None:
    script = HBM_DIR / "scripts" / rel
    proc = subprocess.run(
        [sys.executable, "-B", str(script)],
        cwd=str(ROOT),
        env=_apply_env(),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise TestFailure(
            f"{name} failed:\n{proc.stdout}\n{proc.stderr}"
        )
    ok(f"{name} passed")


def _static_f12_checklist() -> None:
    section("F12 static implementation checklist")
    web = WEB_DIR / "src"
    checks = [
        (HBM_DIR / "features" / "f12_world_sync" / "delta.py", "Flask build_world_delta"),
        (HBM_DIR / "http" / "routes.py", "world-snapshot route"),
        (web / "features" / "world-stage" / "WorldStage.tsx", "WorldStage"),
        (web / "store" / "worldSync.ts", "worldSync"),
        (web / "features" / "layout" / "TwoColumnLayout.tsx", "TwoColumnLayout"),
    ]
    for path, label in checks:
        if not path.is_file():
            raise TestFailure(f"missing {label}: {path}")
        ok(label)
    routes = (HBM_DIR / "http" / "routes.py").read_text(encoding="utf-8")
    if "world-snapshot" not in routes:
        raise TestFailure("GET /world-snapshot not registered")
    app = (web / "App.tsx").read_text(encoding="utf-8")
    if "ObserverPanel" in app:
        raise TestFailure("App still uses ObserverPanel")
    ok("Flask + frontend F12 artifacts present; Observer removed from App")


def main() -> int:
    print("F12 full-plan acceptance (dev_logs/32 Phases 1–4 automated)")
    failures: list[str] = []

    for name, rel in (
        ("Phase 1 persistence", "test_f12_phase1_persistence.py"),
        ("Phase 2 world delta", "test_f12_world_delta.py"),
        ("Phase 4 visibility", "test_f12_visibility.py"),
        ("Synthetic engine replay", "test_f12_synthetic_scenario.py"),
    ):
        try:
            _run_py(name, rel)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{rel}: {exc}")
            print(f"  ✗ {exc}")

    try:
        _static_f12_checklist()
    except Exception as exc:  # noqa: BLE001
        failures.append(f"static: {exc}")
        print(f"  ✗ {exc}")

    section("Phase 3 worldSync TS unit")
    try:
        proc = subprocess.run(
            ["npx", "--yes", "tsx", str(WEB_DIR / "scripts" / "test_world_sync.ts")],
            cwd=str(WEB_DIR),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise TestFailure(proc.stdout + proc.stderr)
        ok("worldSync.ts passed")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"world_sync_ts: {exc}")
        print(f"  ✗ {exc}")

    section("Frontend production build")
    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(WEB_DIR),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise TestFailure(proc.stdout + proc.stderr)
        ok("npm run build passed")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"npm_build: {exc}")
        print(f"  ✗ {exc}")

    section("M0 acceptance + F12 E2E (Runner/Flask/Turn1)")
    try:
        _run_py("test_m0_acceptance", "test_m0_acceptance.py")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"m0: {exc}")
        print(f"  ✗ {exc}")

    if failures:
        print(f"\nFAILED ({len(failures)}):")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("\n" + "=" * 50)
    print("ALL F12 FULL-PLAN AUTOMATED TESTS PASSED")
    print("Manual Phase 4: Turn1–4 UI walkthrough (routing moves, Turn16 broadcast)")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

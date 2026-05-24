#!/usr/bin/env python3
"""M0–M7 acceptance tests — dev_logs/26 §7 (M7: legacy shim cleanup)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import http.client
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[3]
HBM_DIR = ROOT / "agent_world" / "hbm_demo"
SIM_DIR = HBM_DIR / "sim" / "hbm_memory_war"
SIM_ID = "hbm_memory_war"
BASE_PATH = f"/api/hbm/simulations/{SIM_ID}"

_LLM_KEY_PLACEHOLDERS = frozenset({"", "sk-your-key-here", "sk-..."})


class TestFailure(Exception):
    pass


def load_env_file_into(env: Dict[str, str], path: Path) -> None:
    """Mirror start_demo.sh load_env_file — do not override existing keys."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in env:
            env[key] = val


def apply_hbm_demo_env(env: Dict[str, str]) -> Dict[str, str]:
    """Load hbm_demo/.env and agent_world/demo/.env into subprocess env."""
    load_env_file_into(env, HBM_DIR / ".env")
    load_env_file_into(env, ROOT / "agent_world" / "demo" / ".env")
    return env


def llm_api_key_configured(env: Dict[str, str] | None = None) -> bool:
    val = str((env or os.environ).get("DMXAPI_KEY") or "").strip()
    return bool(val) and val not in _LLM_KEY_PLACEHOLDERS


def runner_log_excerpt(max_lines: int = 30) -> str:
    log_path = HBM_DIR / "scripts" / ".run" / "m0_runner.log"
    if not log_path.is_file():
        return "(no m0_runner.log)"
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _message_key(message: Dict[str, Any]) -> str:
    """Mirror web/src/utils/messages.ts messageKey for F11-C dedupe tests."""
    return "|".join(
        [
            str(message.get("type") or ""),
            str(message.get("sender") or ""),
            str(message.get("recipient") or ""),
            str(message.get("group_id") or ""),
            str(message.get("attempted_at") or ""),
            str(message.get("content") or ""),
        ]
    )


def merge_message_lists(
    existing: List[Dict[str, Any]],
    incoming: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Mirror web mergeMessages — used to verify F11-C delta+completed dedupe."""
    seen = {_message_key(m) for m in existing}
    merged = list(existing)
    for message in incoming:
        key = _message_key(message)
        if key in seen:
            continue
        seen.add(key)
        merged.append(message)
    return merged


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def http_json(
    method: str,
    url: str,
    *,
    body: Dict[str, Any] | None = None,
    cookie: str = "",
    timeout: float = 120.0,
) -> Tuple[int, Dict[str, Any], str]:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    if parsed.query:
        path = f"{path}?{parsed.query}"

    headers = {"Accept": "application/json", "Connection": "close"}
    payload_bytes: bytes | None = None
    if method.upper() in ("POST", "PUT", "PATCH"):
        headers["Content-Type"] = "application/json"
        payload_bytes = json.dumps(body if body is not None else {}).encode("utf-8")
    if cookie:
        headers["Cookie"] = cookie

    conn = http.client.HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port or 80, timeout=timeout)
    try:
        conn.request(method.upper(), path, body=payload_bytes, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        set_cookie = resp.getheader("Set-Cookie")
        if set_cookie:
            cookie = set_cookie.split(";", 1)[0]
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return resp.status, payload, cookie
    finally:
        conn.close()


def poll_action_result(
    base: str,
    task_id: str,
    cookie: str,
    *,
    max_wait: float = 180.0,
) -> Tuple[Dict[str, Any], str]:
    deadline = time.time() + max_wait
    url = f"{base}{BASE_PATH}/action-result?task_id={task_id}"
    last: Dict[str, Any] = {}
    while time.time() < deadline:
        code, payload, cookie = http_json("GET", url, cookie=cookie, timeout=30.0)
        if code != 200:
            raise TestFailure(f"action-result HTTP {code}: {payload}")
        last = payload.get("data") or {}
        if last.get("status") == "completed":
            return last, cookie
        if last.get("status") == "failed":
            raise TestFailure(f"action-result failed: {last}")
        time.sleep(1.0)
    raise TestFailure(f"action-result timeout after {max_wait}s; last={last}")


def test_static_imports() -> None:
    section("T1 静态 import 与 FEATURE_REGISTRY")
    from agent_world.hbm_demo.features import FEATURE_REGISTRY

    if len(FEATURE_REGISTRY) < 10:
        raise TestFailure(f"FEATURE_REGISTRY expected >=10, got {len(FEATURE_REGISTRY)}")
    ok(f"FEATURE_REGISTRY: {len(FEATURE_REGISTRY)} features")

    from agent_world.hbm_demo.features.f05_story_routing import routing

    if routing.inject_agent_ids_for_phase("Phase 1") != [1]:
        raise TestFailure("F05 Phase 1 inject agents != [1]")
    ok("F05 inject_agent_ids_for_phase Phase 1 → [1]")

    from agent_world.hbm_demo import game_service as gs

    if not hasattr(gs, "handle_player_turn") or not hasattr(gs, "reset_demo"):
        raise TestFailure("game_service missing handle_player_turn or reset_demo")
    ok("game_service orchestration entrypoints present")

    from agent_world.hbm_demo.core.runner.ipc_handlers import wire_handlers  # noqa: F401

    ok("core.runner.ipc_handlers imports")


def test_m1_shared_modules() -> None:
    section("T1b M1 shared/ 模块")
    from agent_world.hbm_demo import shared
    from agent_world.hbm_demo.shared import (
        config_loader,
        env_status,
        errors,
        settings,
    )

    if not callable(env_status.is_runner_ready):
        raise TestFailure("shared.env_status.is_runner_ready missing")
    ok("shared.env_status.is_runner_ready")

    if not hasattr(settings, "DEFAULT_IPC_TIMEOUT"):
        raise TestFailure("shared.settings.DEFAULT_IPC_TIMEOUT missing")
    ok("shared.settings.DEFAULT_IPC_TIMEOUT")

    if not hasattr(errors, "RunnerNotReadyError"):
        raise TestFailure("shared.errors.RunnerNotReadyError missing")
    ok("shared.errors.RunnerNotReadyError")

    scenario = config_loader.load_scenario(HBM_DIR / "hbm_scenario.yaml")
    if scenario.get("simulation_id") != SIM_ID:
        raise TestFailure(f"load_scenario simulation_id != {SIM_ID}")
    ok(f"shared.load_scenario → {SIM_ID}")

    if "DEFAULT_IPC_TIMEOUT" not in shared.__all__:
        raise TestFailure("shared.__all__ missing DEFAULT_IPC_TIMEOUT")
    ok("shared/__init__.py re-exports")


def test_m2_game_service_shims() -> None:
    section("T1c M2 game_service 拆分与根 shim")
    import agent_world.hbm_demo.game_service as root_gs
    from agent_world.hbm_demo.features.f01_session.models import HbmSession
    from agent_world.hbm_demo.features.f02_player_turn.handler import handle_player_turn
    from agent_world.hbm_demo.features.f03_action_result.handler import get_action_result
    from agent_world.hbm_demo.features.f04_stats.scoring import score_player_turn
    from agent_world.hbm_demo.features.f06_read_model.world_db import ReadOnlyWorldDB

    pairs = (
        ("HbmSession", root_gs.HbmSession, HbmSession),
        ("handle_player_turn", root_gs.handle_player_turn, handle_player_turn),
        ("get_action_result", root_gs.get_action_result, get_action_result),
        ("score_player_turn", root_gs.score_player_turn, score_player_turn),
        ("ReadOnlyWorldDB", root_gs.ReadOnlyWorldDB, ReadOnlyWorldDB),
    )
    for name, root_obj, feat_obj in pairs:
        if root_obj is not feat_obj:
            raise TestFailure(f"game_service.{name} shim != feature implementation")
        ok(f"game_service.{name}")

    shim_lines = (HBM_DIR / "game_service.py").read_text(encoding="utf-8").count("\n")
    if shim_lines > 120:
        raise TestFailure(f"game_service.py shim too large: {shim_lines} lines")
    ok(f"game_service.py shim size OK ({shim_lines} lines)")


def test_m3_runner_modules() -> None:
    section("T1d M3 core/runner/ 模块与 run_hbm 入口 shim")
    import agent_world.hbm_demo.run_hbm as root_run
    from agent_world.hbm_demo.core.runner import hbm_agent, ipc_handlers, kernel, run_hbm

    if root_run.main is not run_hbm.main:
        raise TestFailure("run_hbm.py shim != core.runner.run_hbm.main")
    ok("run_hbm.py shim → core.runner.run_hbm.main")

    for name, obj in (
        ("kernel.build_kernel", kernel.build_kernel),
        ("kernel.resolve_api_key", kernel.resolve_api_key),
        ("ipc_handlers.wire_handlers", ipc_handlers.wire_handlers),
        ("hbm_agent.HbmAgent", hbm_agent.HbmAgent),
    ):
        if not callable(obj) and not isinstance(obj, type):
            raise TestFailure(f"{name} missing")
        ok(name)

    from agent_world.ipc.commands import CommandType

    registered = {
        CommandType.INJECT_SCRIPT_EVENT,
        CommandType.LIST_PLACES,
        CommandType.MOVE_AGENT,
        CommandType.RESET_WORLD,
        CommandType.CLOSE_ENV,
    }
    ok(f"IPC CommandType registry includes {len(registered)} F00 commands")


def test_m4_http_modules() -> None:
    section("T1e M4 http/ 模块与 routes 入口 shim")
    import agent_world.hbm_demo.routes as root_routes
    from agent_world.hbm_demo.http import health, http_errors, ipc_helper, routes as http_routes

    if root_routes.hbm_bp is not http_routes.hbm_bp:
        raise TestFailure("routes.py shim != http.routes.hbm_bp")
    ok("routes.py shim → http.routes.hbm_bp")

    for name, obj in (
        ("ipc_helper.send_inject_batch", ipc_helper.send_inject_batch),
        ("health.check_stack_health", health.check_stack_health),
        ("http_errors.service_error_payload", http_errors.service_error_payload),
    ):
        if not callable(obj):
            raise TestFailure(f"{name} missing")
        ok(name)

    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(http_routes.hbm_bp)
    rules = {r.rule for r in app.url_map.iter_rules() if r.rule != "/static/<path:filename>"}
    expected = {
        "/simulations/<sim_id>/session/start",
        "/simulations/<sim_id>/session/reset",
        "/simulations/<sim_id>/session",
        "/simulations/<sim_id>/health",
        "/simulations/<sim_id>/env-status",
        "/simulations/<sim_id>/player-turn",
        "/simulations/<sim_id>/action-result",
        "/simulations/<sim_id>/debug-inject",
    }
    if rules != expected:
        raise TestFailure(f"hbm_bp routes mismatch: {sorted(rules)}")
    ok(f"hbm_bp registers {len(expected)} HTTP endpoints (F08)")


def test_f11_live_turn_sync() -> None:
    section("T1i F11 Live Turn Sync (F11-A)")
    from agent_world.hbm_demo.features import FEATURE_REGISTRY
    from agent_world.hbm_demo.features.f02_player_turn.task import (
        INJECT_STATUS_RUNNING,
        PendingTask,
    )
    from agent_world.hbm_demo.features.f11_live_turn_sync.handler import (
        start_background_turn,
    )
    from agent_world.hbm_demo.features.f11_live_turn_sync.task_state import (
        sync_runtime_state,
    )

    if "F11" not in FEATURE_REGISTRY:
        raise TestFailure("FEATURE_REGISTRY missing F11")
    ok("FEATURE_REGISTRY includes F11")

    task = PendingTask(
        task_id="t",
        start_tick=0,
        place_id="nvidia_reception",
        phase="Phase 1",
        player_turn=1,
        inject_status=INJECT_STATUS_RUNNING,
    )
    if task.to_dict().get("inject_status") != INJECT_STATUS_RUNNING:
        raise TestFailure("PendingTask inject_status not serialized")
    ok("PendingTask inject_status field")

    if not callable(start_background_turn) or not callable(sync_runtime_state):
        raise TestFailure("F11 entrypoints missing")
    ok("F11 start_background_turn + sync_runtime_state")

    from agent_world.hbm_demo.features.f02_player_turn.task import INJECT_STATUS_DONE
    from agent_world.hbm_demo.features.f03_action_result.completion import (
        check_action_complete,
    )
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_f07_enabled,
    )

    class EmptyDB:
        def has_f2f_after(self, *a, **k):
            return False

        def has_rdc_pair_after(self, *a, **k):
            return False

        def has_grp_after(self, *a, **k):
            return False

    running = PendingTask(
        task_id="t-run",
        start_tick=0,
        place_id="nvidia_reception",
        phase="Phase 1",
        player_turn=1,
        inject_status=INJECT_STATUS_RUNNING,
        ipc_end_tick=None,
    )
    if check_action_complete(running, 6, EmptyDB()):
        raise TestFailure("F11: running inject must not complete via ipc_end alone at tick 6")
    ok("F11 inject_status=running blocks ipc_end premature complete")

    done_tick = 8 if is_f07_enabled() else 6
    done = PendingTask(
        task_id="t-done",
        start_tick=0,
        place_id="nvidia_reception",
        phase="Phase 1",
        player_turn=1,
        inject_status=INJECT_STATUS_DONE,
        ipc_end_tick=done_tick,
    )
    if not check_action_complete(done, done_tick, EmptyDB()):
        raise TestFailure(
            f"F11: done inject should complete at ipc_end_tick={done_tick}"
        )
    ok(f"F11 inject_status=done + ipc_end_tick={done_tick} completes")

    from agent_world.hbm_demo.features.f11_live_turn_sync.task_state import (
        async_state_path,
        clear_async_state,
    )

    clear_async_state(SIM_DIR)
    if async_state_path(SIM_DIR).exists():
        raise TestFailure("clear_async_state should remove runtime.json")
    ok("F11 clear_async_state")

    from agent_world.hbm_demo.features.f11_live_turn_sync.delta import (
        build_turn_delta,
        empty_delta,
    )

    ed = empty_delta(3)
    if ed.get("through_tick") != 3 or ed.get("public_messages") != []:
        raise TestFailure(f"empty_delta wrong: {ed}")
    ok("F11-B empty_delta")

    class _Row(dict):
        def __getitem__(self, key):  # noqa: ANN001
            return dict.__getitem__(self, key)

    class FakeDB:
        def fetch_f2f_history_at(self, place_id, t_now, since_t):  # noqa: ANN001
            return [(2, 1, 1, "前台你好"), (4, 1, 2, "请稍等")]

        def fetch_messages_since(self, *, channel_type, since_t, t_now):  # noqa: ANN001
            if channel_type == "RDC" and since_t < 3:
                return [
                    _Row(
                        channel_type="RDC",
                        sender_id=2,
                        recipient_id=3,
                        group_id=None,
                        content="内参",
                        place_id="",
                        attempted_at=3,
                    )
                ]
            if channel_type == "GRP":
                return [
                    _Row(
                        channel_type="GRP",
                        sender_id=4,
                        recipient_id=None,
                        group_id=100,
                        content="群消息",
                        place_id="negotiation_room",
                        attempted_at=5,
                    )
                ]
            return []

    task = PendingTask(
        task_id="t-delta",
        start_tick=0,
        place_id="nvidia_reception",
        phase="Phase 1",
        player_turn=1,
        inject_status=INJECT_STATUS_RUNNING,
    )
    name_map = {1: "接待前台", 2: "Jensen", 3: "Tech VP", 4: "AMD"}
    delta = build_turn_delta(task, since_tick=1, effective_tick=6, db=FakeDB(), name_map=name_map)
    if delta.get("through_tick") != 6:
        raise TestFailure(f"delta through_tick != 6: {delta}")
    if len(delta.get("public_messages") or []) != 2:
        raise TestFailure(f"expected 2 F2F after since_tick=1: {delta}")
    if len(delta.get("observer_messages") or []) != 1:
        raise TestFailure(f"expected 1 RDC: {delta}")
    if len(delta.get("group_messages") or []) != 1:
        raise TestFailure(f"expected 1 GRP: {delta}")
    ok("F11-B build_turn_delta filters since_tick")


def test_f11_c_frontend() -> None:
    section("T1j F11-C 前端增量合并")
    web_src = HBM_DIR / "web" / "src"

    game_loop = (web_src / "features" / "game-loop" / "useGameLoop.ts").read_text(
        encoding="utf-8"
    )
    if "APPEND_TURN_DELTA" not in game_loop or "since_tick" not in game_loop:
        raise TestFailure("useGameLoop missing F11-C delta poll merge")
    ok("useGameLoop APPEND_TURN_DELTA + since_tick poll")

    store = (web_src / "store" / "gameStore.ts").read_text(encoding="utf-8")
    if "APPEND_TURN_DELTA" not in store:
        raise TestFailure("gameStore missing APPEND_TURN_DELTA reducer")
    ok("gameStore APPEND_TURN_DELTA reducer")

    hbm_api = (web_src / "api" / "hbm.ts").read_text(encoding="utf-8")
    if "since_tick" not in hbm_api:
        raise TestFailure("hbm.ts getActionResult missing since_tick")
    ok("api/hbm.ts since_tick query param")

    import re

    game_loop_const = (web_src / "constants" / "gameLoop.ts").read_text(encoding="utf-8")
    if not re.search(r"POLL_INTERVAL_MS\s*=\s*800", game_loop_const):
        raise TestFailure("gameLoop POLL_INTERVAL_MS should be 800 for F11-C")
    ok("POLL_INTERVAL_MS = 800ms")

    messages = (web_src / "utils" / "messages.ts").read_text(encoding="utf-8")
    if "messageKey" not in messages or "mergeMessages" not in messages:
        raise TestFailure("utils/messages dedupe helpers missing")
    ok("messageKey dedupe for delta merge")


def test_f03_action_completion() -> None:
    section("T1f F03 action-result 完成判定")
    from agent_world.hbm_demo.features.f02_player_turn.task import (
        INJECT_STATUS_DONE,
        PendingTask,
    )
    from agent_world.hbm_demo.features.f03_action_result.completion import (
        RECEPTION_PLACE,
        check_action_complete,
    )
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_f07_enabled,
    )

    class EmptyDB:
        def has_f2f_after(self, *a, **k):
            return False

        def has_rdc_pair_after(self, *a, **k):
            return False

        def has_grp_after(self, *a, **k):
            return False

    class RdcOnlyDB(EmptyDB):
        def has_rdc_pair_after(self, *a, **k):
            return True

    class F2fReceptionDB(EmptyDB):
        def has_f2f_after(self, place_id, *a, **k):
            return place_id == RECEPTION_PLACE

    task_p1 = PendingTask(
        task_id="t1",
        start_tick=0,
        place_id="nvidia_reception",
        phase="Phase 1",
        player_turn=1,
        ipc_end_tick=6,
        inject_status=INJECT_STATUS_DONE,
    )
    if is_f07_enabled():
        if check_action_complete(task_p1, 6, RdcOnlyDB()):
            raise TestFailure("F07 Phase 1 must not complete on RDC alone (§13.2)")
        ok("F07 Phase 1 ignores RDC-only completion")
        if check_action_complete(task_p1, 6, EmptyDB()):
            raise TestFailure("F07 Phase 1 should not complete at tick 6 without F2F")
        if not check_action_complete(task_p1, 8, EmptyDB()):
            raise TestFailure("F07 Phase 1 should timeout-complete at tick 8")
        if not check_action_complete(task_p1, 5, F2fReceptionDB()):
            raise TestFailure("F07 Phase 1 should complete on reception F2F")
        ok("F07 Phase 1 F2F-priority completion (§13.2)")
    else:
        if not check_action_complete(task_p1, 6, EmptyDB()):
            raise TestFailure("F03 should complete when ipc_end_tick reached (6-tick inject)")
        ok("F03 completes after ipc_end_tick without hanging")

    task_p2 = PendingTask(
        task_id="t2",
        start_tick=0,
        place_id="jensen_private_room",
        phase="Phase 2",
        player_turn=5,
        ipc_end_tick=6,
    )
    if not check_action_complete(task_p2, 6, EmptyDB()):
        raise TestFailure("Phase 2 should still complete at ipc_end_tick")
    ok("Phase 2 ipc_end_tick completion unchanged")


def test_f07_b_agent_control() -> None:
    """F07-B L3/L5 unit tests (dev_logs/24 §11 B1–B5)."""
    section("T2d F07-B pick_active / tool_guard / world_step")
    from types import SimpleNamespace

    from agent_world.demo.demo_agent import _ToolCall
    from agent_world.hbm_demo.core.runner.world_step import HbmWorldStep
    from agent_world.hbm_demo.features.f07_agent_control import (
        is_tool_allowed,
        pick_active_ids,
        primary_active_ids,
    )
    from agent_world.hbm_demo.features.f07_agent_control.tool_guard import (
        filter_tool_calls,
    )

    ctx_p1 = {
        "phase": "Phase 1",
        "player_turn": 1,
        "place_id": "nvidia_reception",
        "llm_params": {"temperature": 0.45, "max_tokens": 180},
    }
    primary = primary_active_ids(ctx_p1)
    if primary != [1, 2, 3]:
        raise TestFailure(f"Phase 1 primary_active expected [1,2,3]: {primary}")
    ok("B4 Phase 1 primary_active [1,2,3]")

    world = SimpleNamespace(agents={1: object(), 2: object(), 3: object(), 7: object()})
    active = pick_active_ids(ctx_p1, world, t=10)
    if 7 in active:
        raise TestFailure(f"Phase 1 must freeze agent 7: {active}")
    if not all(aid in (1, 2, 3, 4, 5, 6) for aid in active):
        raise TestFailure(f"Phase 1 active out of range: {active}")
    if not all(aid in active for aid in (1, 2, 3)):
        raise TestFailure(f"Phase 1 must include primary [1,2,3]: {active}")
    ok(f"B1 pick_active Phase 1 active={active} (no agent 7)")

    if is_tool_allowed(2, "request_move", ctx_p1):
        raise TestFailure("Phase 1 must block request_move")
    if is_tool_allowed(1, "send_to_group", ctx_p1):
        raise TestFailure("Phase 1 agent 1 must block send_to_group")
    if not is_tool_allowed(1, "speak_to_local", ctx_p1):
        raise TestFailure("Phase 1 agent 1 must allow speak_to_local")
    ok("B3 tool_guard MOVE/GRP blocked Phase 1")

    blocked = filter_tool_calls(
        2,
        ctx_p1,
        [_ToolCall(tool_name="request_move", args={"place_id": "x"})],
    )
    if not blocked or blocked[0].tool_name != "do_nothing":
        raise TestFailure(f"blocked MOVE should become do_nothing: {blocked}")
    ok("B3 filter_tool_calls replaces illegal MOVE")

    step = HbmWorldStep.__new__(HbmWorldStep)
    step._tick_context = None
    step._passive_ticks_batch = 0
    step.set_tick_context(ctx_p1)
    if step._passive_ticks_batch != 0:
        raise TestFailure("set_tick_context should reset passive counter")
    step.clear_tick_context()
    if step._tick_context is not None:
        raise TestFailure("clear_tick_context failed")
    ok("B2 world_step tick_context set/clear hooks")

    from agent_world.hbm_demo.features.f07_agent_control.config import (
        resolve_inject_tick_count,
    )

    if resolve_inject_tick_count("Phase 1", 6) != 8:
        raise TestFailure("F07 Phase 1 inject tick_count should floor at 8 (§13.2)")
    if resolve_inject_tick_count("Phase 2", 6) != 6:
        raise TestFailure("Phase 2 tick_count should stay unchanged")
    ok("B5 Phase 1 inject tick_count ≥8 for completion timeout")


def test_f07_c_agent_control() -> None:
    """F07-C Phase 2–3 polish + nodes B/C (dev_logs/24 §11 C1–C4)."""
    section("T2e F07-C Phase 2/3 L6 + nodes B/C")
    from types import SimpleNamespace

    from agent_world.hbm_demo.features.f05_story_routing.routing import (
        POSITIVE_RDC_KEYWORDS,
        node_b_applies,
        node_c_applies,
    )
    from agent_world.hbm_demo.features.f07_agent_control.knowledge import (
        build_agent_knowledge,
        load_turn_hints,
    )
    from agent_world.hbm_demo.features.f07_agent_control.llm_params import (
        resolve_llm_params,
    )
    from agent_world.hbm_demo.features.f07_agent_control.pick_active import (
        _has_unread_inbound,
        _passive_candidates,
        primary_active_ids,
    )
    from agent_world.hbm_demo.features.f07_agent_control.player_response import (
        format_l6_player_directive,
        format_notification_directive,
    )

    ctx_p2 = {
        "phase": "Phase 2",
        "player_turn": 7,
        "place_id": "jensen_private_room",
        "llm_params": {"temperature": 0.5, "max_tokens": 220},
    }
    if primary_active_ids(ctx_p2) != [2]:
        raise TestFailure(f"Phase 2 primary must be [2]: {primary_active_ids(ctx_p2)}")
    ok("C1 Phase 2 primary_active [2]")

    world_p2 = SimpleNamespace(
        agents={2: object(), 3: object()},
        db=SimpleNamespace(
            fetch_arrived_for=lambda aid, t, last: (
                [SimpleNamespace(sender_id=2)] if aid == 3 else []
            )
        ),
        places=SimpleNamespace(L_t=lambda aid: "negotiation_room"),
    )
    agent3 = SimpleNamespace(last_message_seen_at=0)
    if not _has_unread_inbound(3, agent3, world_p2, 5, rdc_from=2):
        raise TestFailure("C1 VP should detect unread Jensen RDC")
    if _has_unread_inbound(3, agent3, world_p2, 5, rdc_from=4):
        raise TestFailure("C1 VP must ignore non-Jensen RDC (rdc_from=2 only)")
    passive = _passive_candidates("Phase 2", 7, world_p2, 5, world_p2.agents)
    if 3 not in passive:
        raise TestFailure(f"C1 Phase 2 passive list missing VP: {passive}")
    ok(f"C1 Phase 2 passive VP when Jensen→3 RDC: {passive}")

    vp_note = format_notification_directive(
        phase="Phase 2", player_turn=8, agent_id=3
    )
    if "Jensen" not in vp_note or "可行" not in vp_note:
        raise TestFailure(f"C1 VP notification missing §13.3 hints: {vp_note[:80]}")
    ok("C1 Phase 2 VP notification §13.3")

    p3_jensen = format_l6_player_directive(
        agent_id=2,
        phase="Phase 3",
        player_turn=16,
        player_text="AMD 新闻反而证明我们需要降 HBM 方案",
    )
    if "帮玩家" not in p3_jensen or "Turn 16" not in p3_jensen:
        raise TestFailure("C2 Phase 3 Jensen L6 missing 帮玩家/Turn16")
    p3_ceo = format_l6_player_directive(
        agent_id=4,
        phase="Phase 3",
        player_turn=14,
        player_text="HBM 需求可被稀疏方案降低",
    )
    if "CEO 进攻" not in p3_ceo and "攻击玩家" not in p3_ceo:
        raise TestFailure("C2 Phase 3 CEO L6 missing attack directive")
    ok("C2 Phase 3 L6 帮玩家 / CEO 进攻")

    llm16 = resolve_llm_params("Phase 3", 16)
    if llm16.get("temperature") != 0.68 or llm16.get("max_tokens") != 400:
        raise TestFailure(f"C2 Turn 16 llm_params wrong: {llm16}")
    ok("C2 Turn 16 temperature/max_tokens override")

    session_p3 = SimpleNamespace(
        phase="Phase 3",
        player_turn=16,
        place_id="negotiation_room",
        stats={"vision": 25, "execution": 22, "trust": 30, "burnout": 40},
    )
    block_p3 = build_agent_knowledge(
        session_p3, 2, "稀疏 KV 可降 HBM 需求", channel="inject"
    )
    if "帮玩家" not in block_p3 or "Turn 16" not in block_p3:
        raise TestFailure("C2 inject knowledge missing Phase 3 help-player block")
    ok("C2 build_agent_knowledge Phase 3 Turn 16")

    hints = load_turn_hints()
    short = [t for t in range(1, 26) if len(hints.get(t, "")) < 80]
    if short:
        raise TestFailure(f"C3 turn_hints still short (<80): {short[:5]}")
    ok(f"C3 turn_hints all ≥80 chars (sample Turn 12={len(hints[12])})")

    class FakeDB:
        def __init__(self, rows):
            self._rows = rows

        def fetch_rdc_messages(
            self, *, sender_id, recipient_id, since_t, t_now  # noqa: ANN001
        ):
            return [
                r
                for r in self._rows
                if int(r.get("sender_id", -1)) == int(sender_id)
                and int(r.get("recipient_id", -1)) == int(recipient_id)
            ]

    class SessB:
        player_turn = 12
        phase = "Phase 2"
        stats = {"execution": 22, "vision": 20, "trust": 10, "burnout": 0}
        phase2_start_tick = 40

    pos_row = {"content": "理论上可行，这是核武器", "sender_id": 3, "recipient_id": 2}
    if not node_b_applies(SessB(), FakeDB([pos_row]), 50):
        raise TestFailure("C4 node B should apply with E≥20 + positive VP RDC")
    SessB.stats["execution"] = 10
    if node_b_applies(SessB(), FakeDB([pos_row]), 50):
        raise TestFailure("C4 node B must require execution≥20")
    ok(f"C4 node B (keywords={list(POSITIVE_RDC_KEYWORDS[:2])}…)")

    class SessC:
        player_turn = 20
        phase = "Phase 3"
        stats = {"vision": 35, "execution": 25, "trust": 30, "burnout": 50}

    if not node_c_applies(SessC()):
        raise TestFailure("C4 node C should apply at Turn 20 V≥30 Burnout<80")
    SessC.stats["burnout"] = 90
    if node_c_applies(SessC()):
        raise TestFailure("C4 node C must require burnout<80")
    ok("C4 node C threshold logic")

    probe_env: Dict[str, str] = {}
    apply_hbm_demo_env(probe_env)
    if llm_api_key_configured(probe_env):
        ok("Tier B: DMXAPI_KEY loaded from hbm_demo/.env for E2E")
    else:
        ok("Tier B: no DMXAPI_KEY — E2E will use Tier A only")


def test_m6_frontend_features() -> None:
    section("T1g M6 web/src/features/ 前端 Feature 拆分")
    web_src = HBM_DIR / "web" / "src"
    feature_dirs = (
        "boot",
        "game-loop",
        "layout",
        "main-chat",
        "observer",
        "endings",
        "shared",
    )
    for name in feature_dirs:
        path = web_src / "features" / name
        if not path.is_dir():
            raise TestFailure(f"missing features/{name}/")
        ok(f"features/{name}/ exists")

    registry = (web_src / "features" / "index.ts").read_text(encoding="utf-8")
    if "FEATURE_REGISTRY" not in registry or "F09a" not in registry:
        raise TestFailure("features/index.ts missing FEATURE_REGISTRY")
    ok("features/index.ts FEATURE_REGISTRY (F09a–h)")

    app_src = (web_src / "App.tsx").read_text(encoding="utf-8")
    if 'from "./features"' not in app_src:
        raise TestFailure("App.tsx should import from ./features directly")
    ok("App.tsx imports from ./features")

    for removed in ("components", "hooks"):
        if (web_src / removed).exists():
            raise TestFailure(f"legacy web/src/{removed}/ should be removed (M7)")
    ok("web/src/components and hooks removed (M7)")

    layout_impl = (web_src / "features" / "layout" / "ThreeColumnLayout.tsx").read_text(
        encoding="utf-8"
    )
    if "ThreeColumnLayout" not in layout_impl or "app-shell" not in layout_impl:
        raise TestFailure("features/layout/ThreeColumnLayout implementation missing")
    ok("F09c ThreeColumnLayout in features/layout")


def test_m7_legacy_cleanup() -> None:
    section("T1h M7 旧 shim / 废弃文件已清除")
    removed_backend = (
        "broadcast_helper.py",
        "config_loader.py",
        "env_status.py",
        "errors.py",
        "health.py",
        "hbm_agent.py",
        "http_errors.py",
        "ipc_handlers.py",
        "ipc_helper.py",
        "kernel.py",
        "routing.py",
        "seed.py",
        "settings.py",
        "turn_context.py",
        "world_reset.py",
        "world_step.py",
    )
    for name in removed_backend:
        path = HBM_DIR / name
        if path.exists():
            raise TestFailure(f"legacy shim still present: {name}")
        ok(f"removed {name}")

    kept = ("run_hbm.py", "routes.py", "game_service.py")
    for name in kept:
        path = HBM_DIR / name
        if not path.is_file():
            raise TestFailure(f"required entry shim missing: {name}")
        ok(f"kept {name}")

    root_py = sorted(p.name for p in HBM_DIR.glob("*.py"))
    expected = sorted(["__init__.py", *kept])
    if root_py != expected:
        raise TestFailure(f"unexpected root .py files: {root_py}")
    ok(f"hbm_demo root has only {len(expected)} .py files")

    if (HBM_DIR / "features" / "f07_agent_control").is_dir():
        tc = HBM_DIR / "features" / "f07_agent_control" / "turn_control.yaml"
        if not tc.is_file():
            raise TestFailure("features/f07_agent_control/turn_control.yaml missing")
        ok("features/f07_agent_control/ present (F07 ABCS)")
    else:
        raise TestFailure("features/f07_agent_control/ should exist after F07-A")


def test_f07_agent_control_a() -> None:
    section("T2b F07-A ABCS skeleton")
    from agent_world.hbm_demo.features import FEATURE_REGISTRY
    from agent_world.hbm_demo.features.f07_agent_control import (
        build_turn_context,
        is_f07_enabled,
        resolve_llm_params,
    )
    from agent_world.hbm_demo.features.f07_agent_control.knowledge import (
        build_agent_knowledge,
    )

    if "F07" not in FEATURE_REGISTRY:
        raise TestFailure("FEATURE_REGISTRY missing F07")
    ok("FEATURE_REGISTRY includes F07")

    if not is_f07_enabled():
        raise TestFailure("F07 turn_control.enabled should be true for F07-A")
    ok("F07 enabled")

    class FakeSession:
        phase = "Phase 1"
        player_turn = 2
        place_id = "nvidia_reception"
        stats = {"vision": 5, "execution": 6, "trust": 10, "burnout": 0}

    ctx = build_turn_context(FakeSession(), "我的算法能砍掉 80% 显存")
    if ctx.get("llm_params", {}).get("temperature") != 0.45:
        raise TestFailure(f"Phase 1 llm_params wrong: {ctx}")
    ok("build_turn_context llm_params Phase 1")

    block = build_agent_knowledge(
        FakeSession(), 1, "我的算法能砍掉 80% 显存", channel="inject"
    )
    if len(block) < 800:
        raise TestFailure(f"agent knowledge block too short: {len(block)}")
    if "80%" not in block and "显存" not in block:
        raise TestFailure("inject block should reference player keywords")
    ok(f"build_agent_knowledge inject ({len(block)} chars)")

    p3 = resolve_llm_params("Phase 3", 16)
    if p3.get("temperature") != 0.68:
        raise TestFailure(f"Phase 3 Turn 16 temperature wrong: {p3}")
    ok("resolve_llm_params Phase 3 Turn 16 override")


def test_f07_a_extended() -> None:
    """F07-A extended acceptance (dev_logs/24 §6.5 / §12.1 / §19.2–§19.4)."""
    section("T2c F07-A extended (knowledge / Runner hooks)")
    import yaml
    from types import SimpleNamespace

    from agent_world.hbm_demo.core.runner.hbm_agent import HbmAgent
    from agent_world.hbm_demo.features.f07_agent_control.config import story_knowledge_dir
    from agent_world.hbm_demo.features.f07_agent_control.knowledge import (
        load_agent_overlay,
        load_phase_shared,
        load_turn_hints,
    )
    from agent_world.hbm_demo.features.f07_agent_control.turn_context import (
        clear_player_memory_for_agents,
        extract_inject_agent_ids,
    )
    from agent_world.hbm_demo.features.f05_story_routing.routing import (
        build_inject_payload,
    )

    story = story_knowledge_dir()
    required_shared = (
        "world_state",
        "scene_atmosphere",
        "plot_beats",
        "forbidden_actions",
    )
    for phase_key in ("phase_1", "phase_2", "phase_3", "phase_4"):
        path = story / "shared" / f"{phase_key}.yaml"
        if not path.is_file():
            raise TestFailure(f"missing shared/{phase_key}.yaml")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for field in required_shared:
            if not str(data.get(field) or "").strip():
                raise TestFailure(f"{phase_key}.yaml missing {field}")
        ok(f"shared/{phase_key}.yaml §6.5 fields")

    for aid in range(1, 8):
        overlay = load_agent_overlay(aid)
        for field in ("identity", "speech_style", "player_stance"):
            if not str(overlay.get(field) or "").strip():
                raise TestFailure(f"agent_{aid}.yaml missing {field}")
        if not (overlay.get("phase_overrides") or {}).get("Phase 1"):
            raise TestFailure(f"agent_{aid}.yaml missing phase_overrides.Phase 1")
    ok("agents/agent_1..7.yaml §6.5 fields")

    hints = load_turn_hints()
    missing = [t for t in range(1, 26) if t not in hints or len(hints[t]) < 80]
    too_long = [t for t in range(1, 26) if t in hints and len(hints[t]) > 220]
    if missing:
        raise TestFailure(f"turn_hints missing or <80 chars for turns: {missing[:5]}…")
    if too_long:
        raise TestFailure(f"turn_hints too long (>220) for turns: {too_long[:3]}…")
    ok("turn_hints Turn 1–25 present (80–200 字 · F07-C)")

    class FakeSession:
        phase = "Phase 1"
        player_turn = 1
        place_id = "nvidia_reception"
        stats = {"vision": 0, "execution": 0, "trust": 10, "burnout": 0}

    for phase in ("Phase 1", "Phase 2", "Phase 3", "Phase 4"):
        FakeSession.phase = phase
        FakeSession.player_turn = {"Phase 1": 1, "Phase 2": 5, "Phase 3": 13, "Phase 4": 21}[
            phase
        ]
        events, _, ctx = build_inject_payload(
            FakeSession(), "测试玩家输入", task_id=f"t_{phase}"
        )
        if not events:
            raise TestFailure(f"no inject events for {phase}")
        if ctx is None:
            raise TestFailure(f"turn_context missing for {phase}")
        text = events[0]["effect"].get("text") or ""
        for marker in ("【本 Phase 世界态】", "【本 Phase 剧情要点】", "【你的角色与目标】"):
            if marker not in text:
                raise TestFailure(f"{phase} inject missing {marker}")
    ok("inject prefix §6.6 structure all Phases")

    events = [
        {
            "effect": {
                "type": "dialogue_injection",
                "agent_id": 1,
                "text": "x",
            }
        }
    ]
    if extract_inject_agent_ids(events) != [1]:
        raise TestFailure("extract_inject_agent_ids failed")
    agents = {
        1: HbmAgent(agent_id=1, name="前台", player_memory=[{"role": "system", "content": "old"}]),
    }
    clear_player_memory_for_agents(agents, [1])
    if agents[1].player_memory:
        raise TestFailure("A6: player_memory not cleared")
    ok("A6 clear_player_memory_for_agents")

    agent = HbmAgent(
        agent_id=1,
        name="前台",
        minutes_per_tick=2,
    )
    agent.current_state_set_at = 0
    agent.player_memory.append({"role": "system", "content": "玩家说：测试"})
    obs = SimpleNamespace(
        self_location="nvidia_reception",
        co_located_agents=[],
        available_places_brief=[],
        contacts=[],
        incoming_messages=[],
        outgoing_messages=[],
        group_messages=[],
        f2f_history=[],
        overheard=[],
        recent_failed_attempts=[],
        group_events=[],
        recent_arrivals=[],
        recent_departures=[],
        scripted_notification=None,
    )
    text = agent._observation_to_text(obs, t=50)
    if "本拍必须且只能调用 update_state" in text:
        raise TestFailure("A8: stale force update_state not skipped with player_memory")
    if "必须选 1 个动作；必须推进剧情" in text:
        raise TestFailure("A7: Demo 10-rule tail still present with player_memory")
    if "HBM Demo · F07" not in text:
        raise TestFailure("A7: HBM short rules missing")
    ok("A7/A8 HbmAgent observation tail with player_memory")

    tc_path = HBM_DIR / "features" / "f07_agent_control" / "turn_control.yaml"
    raw = yaml.safe_load(tc_path.read_text(encoding="utf-8")) or {}
    if not raw.get("llm_params", {}).get("Phase 1"):
        raise TestFailure("turn_control.yaml missing llm_params.Phase 1")
    ok("turn_control.yaml §9.4 llm_params table")


def test_f05_routing_payload() -> None:
    section("T2 F05 剧情路由 payload 单元")
    from agent_world.hbm_demo.features.f05_story_routing.routing import (
        build_inject_payload,
        node_a_applies,
    )
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        load_turn_control,
    )

    class FakeSession:
        phase = "Phase 1"
        player_turn = 1
        place_id = "nvidia_reception"
        stats = {"vision": 0, "execution": 0, "trust": 10, "burnout": 0}

    events, broadcast, turn_context = build_inject_payload(
        FakeSession(), "你好", task_id="t1"
    )
    if len(events) != 1 or events[0]["effect"]["agent_id"] != 1:
        raise TestFailure(f"Phase 1 Turn 1 inject wrong: {events}")
    text = events[0]["effect"].get("text") or ""
    if load_turn_control().get("enabled"):
        if "系统约束" not in text:
            raise TestFailure("F07 enabled: Phase 1 inject must include 系统约束 prefix")
        if len(text) < 800:
            raise TestFailure(
                f"F07 enabled: inject prefix too short ({len(text)} chars, need >=800)"
            )
        if turn_context is None or "llm_params" not in turn_context:
            raise TestFailure("F07 enabled: turn_context must include llm_params")
        ok(f"Phase 1 Turn 1 → F07 inject prefix ({len(text)} chars)")
    else:
        if "系统约束" in text:
            raise TestFailure("F07 disabled: inject should not include ABCS prefix")
        ok("Phase 1 Turn 1 → legacy inject (F07 disabled)")
    if broadcast is not None:
        raise TestFailure("Turn 1 should not broadcast")

    FakeSession.player_turn = 16
    FakeSession.phase = "Phase 3"
    events, broadcast, _ctx = build_inject_payload(
        FakeSession(), "谈判", task_id="t16"
    )
    if broadcast is None:
        raise TestFailure("Turn 16 missing broadcast")
    sam = [e for e in events if e["effect"]["agent_id"] == 7]
    if not sam:
        raise TestFailure("Turn 16 missing Sam inject")
    ok("Turn 16 → AMD broadcast + Sam nudge")

    class NodeA:
        player_turn = 4
        stats = {"vision": 10, "execution": 5, "trust": 10, "burnout": 0}

    if not node_a_applies(NodeA()):
        raise TestFailure("node_a should apply at vision+execution=15")
    ok("F05 node A threshold logic")


def test_runner_module_entry() -> None:
    section("T3 Runner 入口模块")
    import agent_world.hbm_demo.run_hbm as run_hbm

    if not hasattr(run_hbm, "main"):
        raise TestFailure("run_hbm.main missing")
    ok("python -m agent_world.hbm_demo.run_hbm entry intact")


def test_e2e_stack(base: str, *, llm_key: bool = False) -> None:
    section(f"T4 E2E HTTP @ {base}")
    if llm_key:
        ok("Tier B: DMXAPI_KEY configured — LLM smoke assertions enabled")
    else:
        ok("Tier B skipped: no DMXAPI_KEY — code-path assertions only (Tier A)")

    code, health, _ = http_json("GET", f"{base}{BASE_PATH}/health")
    if code != 200:
        raise TestFailure(f"health HTTP {code}: {health}")
    if not (health.get("data") or {}).get("ready"):
        raise TestFailure(f"health not ready: {health}")
    ok("GET /health → ready")

    code, env_payload, _ = http_json("GET", f"{base}{BASE_PATH}/env-status")
    if code != 200:
        raise TestFailure(f"env-status HTTP {code}")
    ok(f"GET /env-status → tick={(env_payload.get('data') or {}).get('current_tick')}")

    code, start, cookie = http_json("POST", f"{base}{BASE_PATH}/session/start")
    if code != 200 or not start.get("success"):
        raise TestFailure(f"session/start failed: {start}")
    data = start.get("data") or {}
    if data.get("player_turn") != 1 or data.get("phase") != "Phase 1":
        raise TestFailure(f"session/start bad state: {data}")
    ok("POST /session/start → Turn 1 Phase 1")

    code, snap, cookie = http_json("GET", f"{base}{BASE_PATH}/session", cookie=cookie)
    if code != 200 or not (snap.get("data") or {}).get("initialized"):
        raise TestFailure(f"GET /session failed: {snap}")
    ok("GET /session → initialized")

    # dev_logs/19 Turn 1 — 高密度技术词，利于前台 F2F / Jensen RDC（Tier B）
    player_text = (
        "我要见黄仁勋。我有一套推理侧稀疏注意力方案，能把大模型 KV Cache "
        "显存占用降低 80%，不是 PPT，是已 repro 的 kernel。"
    )
    t0 = time.time()
    code, turn1, cookie = http_json(
        "POST",
        f"{base}{BASE_PATH}/player-turn",
        body={"player_text": player_text},
        cookie=cookie,
        timeout=120.0,
    )
    post_elapsed = time.time() - t0
    if code != 200 or not turn1.get("success"):
        raise TestFailure(f"player-turn failed HTTP {code}: {turn1}")
    tdata = turn1.get("data") or {}
    task_id = tdata.get("task_id")
    if not task_id:
        raise TestFailure(f"player-turn missing task_id: {tdata}")
    if tdata.get("inject_status") != "running":
        raise TestFailure(f"F11-A: expected inject_status=running, got {tdata}")
    if post_elapsed > 2.0:
        raise TestFailure(
            f"F11-A: player-turn took {post_elapsed:.1f}s, expected <2s (async F04+F11)"
        )
    ok(
        f"POST /player-turn → task_id={task_id[:8]}… inject_status=running "
        f"({post_elapsed:.2f}s early return)"
    )

    section("T4b F11-A/B async inject + delta 运行时验收 (dev_logs/28 §8)")
    start_tick = int(tdata.get("start_tick") or 0)
    saw_tick_advance = False
    saw_processing = False
    saw_inject_running = False
    saw_delta = False
    client_since = start_tick
    last_through = start_tick - 1
    deadline = time.time() + 180.0
    env_url = f"{base}{BASE_PATH}/env-status"
    last_result: Dict[str, Any] = {}
    acc_f2f: List[Dict[str, Any]] = []
    acc_obs: List[Dict[str, Any]] = []
    acc_grp: List[Dict[str, Any]] = []

    while time.time() < deadline:
        _, env_now, cookie = http_json("GET", env_url, cookie=cookie, timeout=15.0)
        env_tick = int((env_now.get("data") or {}).get("current_tick", 0))
        if env_tick > start_tick:
            saw_tick_advance = True

        poll_url = (
            f"{base}{BASE_PATH}/action-result"
            f"?task_id={task_id}&since_tick={client_since}"
        )
        code, poll, cookie = http_json("GET", poll_url, cookie=cookie, timeout=30.0)
        if code != 200:
            raise TestFailure(f"F11 action-result poll HTTP {code}: {poll}")
        last_result = poll.get("data") or {}
        st = last_result.get("status")
        if st == "processing":
            saw_processing = True
            if last_result.get("inject_status") == "running":
                saw_inject_running = True
            delta = last_result.get("delta")
            if delta is None:
                raise TestFailure("F11-B: processing response missing delta")
            saw_delta = True
            through = int(delta.get("through_tick", start_tick - 1))
            if through < last_through:
                raise TestFailure(
                    f"F11-B: through_tick regressed {last_through} → {through}"
                )
            last_through = through
            client_since = through
            acc_f2f = merge_message_lists(
                acc_f2f, delta.get("public_messages") or []
            )
            acc_obs = merge_message_lists(
                acc_obs, delta.get("observer_messages") or []
            )
            acc_grp = merge_message_lists(
                acc_grp, delta.get("group_messages") or []
            )
        if st == "completed":
            break
        if st == "error":
            raise TestFailure(f"F11 inject failed: {last_result}")
        time.sleep(0.5)

    if not saw_tick_advance:
        raise TestFailure(
            f"F11-A: env-status tick did not advance above start_tick={start_tick}"
        )
    ok(f"F11-A env-status tick advanced above start_tick={start_tick}")

    if not saw_processing:
        raise TestFailure("F11-A: never observed action-result status=processing")
    ok("F11-A action-result processing phase observed")

    if saw_inject_running:
        ok("F11-A observed inject_status=running during processing poll")

    if not saw_delta:
        raise TestFailure("F11-B: never received delta on processing poll")
    ok(f"F11-B delta on processing (through_tick reached {last_through})")

    result = last_result
    if result.get("status") != "completed":
        result, cookie = poll_action_result(base, task_id, cookie)

    section("T4c F11-C 增量合并去重 (dev_logs/28 §8 F11-C)")
    final_f2f = merge_message_lists(acc_f2f, result.get("public_messages") or [])
    final_obs = merge_message_lists(acc_obs, result.get("observer_messages") or [])
    final_grp = merge_message_lists(acc_grp, result.get("group_messages") or [])
    baseline_f2f = merge_message_lists([], result.get("public_messages") or [])
    baseline_obs = merge_message_lists([], result.get("observer_messages") or [])
    baseline_grp = merge_message_lists([], result.get("group_messages") or [])
    if len(final_f2f) != len(baseline_f2f):
        raise TestFailure(
            f"F11-C dedupe: F2F count {len(final_f2f)} != completed-only {len(baseline_f2f)}"
        )
    if len(final_obs) != len(baseline_obs):
        raise TestFailure(
            f"F11-C dedupe: observer count {len(final_obs)} != completed-only {len(baseline_obs)}"
        )
    if len(final_grp) != len(baseline_grp):
        raise TestFailure(
            f"F11-C dedupe: GRP count {len(final_grp)} != completed-only {len(baseline_grp)}"
        )
    ok(
        f"F11-C delta+completed dedupe — F2F={len(final_f2f)} observer={len(final_obs)} "
        f"GRP={len(final_grp)} (accumulated during processing: "
        f"{len(acc_f2f)}/{len(acc_obs)}/{len(acc_grp)})"
    )

    runtime_path = SIM_DIR / "async_state" / "runtime.json"
    task_runtime: Dict[str, Any] = {}
    for _ in range(240):
        if runtime_path.is_file():
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
            task_runtime = (runtime.get("tasks") or {}).get(task_id) or {}
            if task_runtime.get("inject_status") == "done":
                break
        time.sleep(0.5)
    else:
        raise TestFailure(
            "F11-A: async_state/runtime.json not written with inject_status=done "
            f"within 120s (last poll result={result.get('status')})"
        )
    if task_runtime.get("ipc_end_tick") is None:
        raise TestFailure("F11-A: runtime ipc_end_tick not set")
    ok(
        f"F11-A runtime.json inject_status=done ipc_end_tick="
        f"{task_runtime.get('ipc_end_tick')}"
    )

    session_overlay = runtime.get("session") or {}
    if int(session_overlay.get("player_turn", 0)) < 2:
        raise TestFailure(
            f"F11-A: session overlay player_turn not incremented: {session_overlay}"
        )
    ok(f"F11-A session overlay player_turn={session_overlay.get('player_turn')}")

    code, sess_after, cookie = http_json("GET", f"{base}{BASE_PATH}/session", cookie=cookie)
    sess_turn = int((sess_after.get("data") or {}).get("player_turn") or 0)
    if sess_turn < 2:
        raise TestFailure(f"F11-A: GET /session player_turn still {sess_turn}")
    ok(f"F11-A GET /session player_turn={sess_turn} after async inject")

    if result.get("status") != "completed":
        raise TestFailure(f"Turn 1 not completed: {result}")
    public = result.get("public_messages") or []
    observer = result.get("observer_messages") or []
    grp = result.get("group_messages") or []
    ok(
        f"GET /action-result completed — F2F={len(public)} observer={len(observer)} "
        f"GRP={len(grp)} turn→{result.get('player_turn')}"
    )

    section("T4d F07 Phase 1 运行时验收 (dev_logs/24 §12.1 · Tier A/B)")
    ipc_end = int(task_runtime.get("ipc_end_tick") or 0)
    if ipc_end < 8:
        raise TestFailure(
            f"F07 Phase 1 inject must reach tick≥8 (§13.2); ipc_end_tick={ipc_end}"
        )
    ok(f"Tier A: ipc_end_tick={ipc_end} (≥8, no processing deadlock)")
    if len(grp) != 0:
        raise TestFailure(
            f"F07 Phase 1 Turn 1 GRP must be 0 (L3/L5); got GRP={len(grp)}"
        )
    ok("Tier A: Phase 1 Turn 1 GRP=0")
    if llm_key:
        if len(public) < 1 and len(observer) < 1:
            raise TestFailure(
                "Tier B: DMXAPI_KEY set but no F2F and no observer RDC — "
                "LLM pipeline may be broken. Last runner log:\n"
                + runner_log_excerpt()
            )
        ok(
            f"Tier B: LLM produced player-visible traffic — "
            f"F2F={len(public)} observer={len(observer)}"
        )
    else:
        if len(public) >= 1 or len(observer) >= 1:
            ok(
                f"Tier B (optional): F2F={len(public)} observer={len(observer)} "
                "(no key gate)"
            )
        else:
            ok(
                "Tier B skipped: no DMXAPI_KEY — F2F=0 observer=0 acceptable"
            )

    section("T5 F01 会话重开 (session/reset)")
    code, reset, cookie = http_json(
        "POST",
        f"{base}{BASE_PATH}/session/reset",
        cookie=cookie,
        timeout=120.0,
    )
    if code != 200 or not reset.get("success"):
        raise TestFailure(f"session/reset failed: {reset}")
    rdata = reset.get("data") or {}
    if rdata.get("player_turn") != 1:
        raise TestFailure(f"reset player_turn != 1: {rdata}")
    ok("POST /session/reset → Turn 1")

    code, env_after, _ = http_json("GET", f"{base}{BASE_PATH}/env-status")
    tick_after = (env_after.get("data") or {}).get("current_tick", -1)
    if tick_after != 0:
        raise TestFailure(f"reset后 tick 应为 0，实际 {tick_after}")
    ok("F01 reset → env tick=0")

    code, turn2, cookie = http_json(
        "POST",
        f"{base}{BASE_PATH}/player-turn",
        body={"player_text": "重开后第一轮测试台词。"},
        cookie=cookie,
        timeout=120.0,
    )
    if code != 200:
        raise TestFailure(f"post-reset player-turn failed: {turn2}")
    task2 = (turn2.get("data") or {}).get("task_id")
    result2, _ = poll_action_result(base, task2, cookie)
    if result2.get("status") != "completed":
        raise TestFailure("post-reset Turn 1 action-result failed")
    ok("重开后 Turn 1 完整回合通过")


def test_frontend_build() -> None:
    section("T6 前端构建")
    web_dir = HBM_DIR / "web"
    if not (web_dir / "node_modules").is_dir():
        subprocess.run(["npm", "install"], cwd=web_dir, check=True, capture_output=True)
    proc = subprocess.run(
        ["npm", "run", "build"],
        cwd=web_dir,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise TestFailure(f"npm run build failed:\n{proc.stderr[-2000:]}")
    ok("npm run build succeeded")


def start_stack() -> Tuple[subprocess.Popen[Any], subprocess.Popen[Any], str, bool]:
    stop = ROOT / "agent_world" / "hbm_demo" / "scripts" / "stop_demo.sh"
    subprocess.run(["bash", str(stop)], check=False, capture_output=True)
    time.sleep(1)

    # Fresh world.db so action-result counts reflect this run only.
    SIM_DIR.mkdir(parents=True, exist_ok=True)
    for stale in (SIM_DIR / "world.db", SIM_DIR / "env_status.json"):
        if stale.exists():
            stale.unlink()

    env = apply_hbm_demo_env(os.environ.copy())
    env["HBM_SIM_DIR"] = str(SIM_DIR)
    env.setdefault("FLASK_RUN_PORT", "5050")
    flask_port = env["FLASK_RUN_PORT"]
    env["FLASK_APP"] = "agent_world.app:create_app"

    python = sys.executable
    run_dir = ROOT / "agent_world" / "hbm_demo" / "scripts" / ".run"
    run_dir.mkdir(parents=True, exist_ok=True)

    runner_log = open(run_dir / "m0_runner.log", "w")
    flask_log = open(run_dir / "m0_flask.log", "w")

    runner = subprocess.Popen(
        [
            python,
            "-m",
            "agent_world.hbm_demo.run_hbm",
            "--config",
            str(HBM_DIR / "hbm_scenario.yaml"),
            "--sim-dir",
            str(SIM_DIR),
            "--log-level",
            "WARNING",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=runner_log,
        stderr=subprocess.STDOUT,
    )

    for _ in range(120):
        from agent_world.hbm_demo.shared.env_status import is_runner_ready

        if is_runner_ready(str(SIM_DIR)):
            break
        if runner.poll() is not None:
            raise TestFailure("Runner exited early; see scripts/.run/m0_runner.log")
        time.sleep(0.5)
    else:
        raise TestFailure("Runner not ready in 60s")

    time.sleep(2.0)

    flask = subprocess.Popen(
        [
            python,
            "-m",
            "flask",
            "run",
            "--host",
            "127.0.0.1",
            "--port",
            flask_port,
        ],
        cwd=str(ROOT),
        env=env,
        stdout=flask_log,
        stderr=subprocess.STDOUT,
    )

    base = f"http://127.0.0.1:{flask_port}"
    health_url = f"{base}{BASE_PATH}/health"
    for _ in range(60):
        try:
            code, payload, _ = http_json("GET", health_url, timeout=5.0)
            if code == 200 and (payload.get("data") or {}).get("ready"):
                return runner, flask, base, llm_api_key_configured(env)
        except (TimeoutError, ConnectionResetError, OSError):
            pass
        if flask.poll() is not None:
            raise TestFailure("Flask exited early; see scripts/.run/m0_flask.log")
        time.sleep(0.5)
    raise TestFailure("Flask health not ready in 30s")


def stop_stack(runner: subprocess.Popen[Any], flask: subprocess.Popen[Any]) -> None:
    for proc in (flask, runner):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> int:
    print("HBM Demo M0–M7 Acceptance Tests (dev_logs/26)")
    failures: List[str] = []

    for fn in (
        test_static_imports,
        test_m1_shared_modules,
        test_m2_game_service_shims,
        test_m3_runner_modules,
        test_m4_http_modules,
        test_f03_action_completion,
        test_m6_frontend_features,
        test_m7_legacy_cleanup,
        test_f07_agent_control_a,
        test_f07_a_extended,
        test_f07_b_agent_control,
        test_f07_c_agent_control,
        test_f05_routing_payload,
        test_f11_live_turn_sync,
        test_f11_c_frontend,
        test_runner_module_entry,
    ):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{fn.__name__}: {exc}")
            print(f"  ✗ {exc}")

    runner = flask = None
    llm_key = False
    try:
        runner, flask, base, llm_key = start_stack()
        test_e2e_stack(base, llm_key=llm_key)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"e2e: {exc}")
        print(f"  ✗ {exc}")
    finally:
        if runner and flask:
            stop_stack(runner, flask)

    try:
        test_frontend_build()
    except Exception as exc:  # noqa: BLE001
        failures.append(f"frontend: {exc}")
        print(f"  ✗ {exc}")

    print("\n" + "=" * 50)
    if failures:
        print(f"FAILED ({len(failures)} issues):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL M0–M7 TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

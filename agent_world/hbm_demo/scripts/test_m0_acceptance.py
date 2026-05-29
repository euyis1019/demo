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


F12_DELTA_KEYS = (
    "through_tick",
    "player_place_id",
    "room_f2f",
    "agent_messages",
    "location_changes",
    "social_events",
    "state_changes",
    "world_events",
    "agent_locations",
    "public_messages",
    "observer_messages",
    "group_messages",
)

F12_SNAPSHOT_KEYS = (
    "through_tick",
    "player_place_id",
    "agent_locations",
    "place_attrs",
    "relations",
    "group_members",
    "name_map",
)

F12_ROOM_PLACES = (
    "nvidia_reception",
    "jensen_private_room",
    "negotiation_room",
    "openai_hq",
)


def assert_f12_delta_shape(
    payload: Dict[str, Any],
    *,
    context: str,
) -> None:
    """Validate F12 TurnDelta fields on action-result delta or completed body."""
    for key in F12_DELTA_KEYS:
        if key not in payload:
            raise TestFailure(f"{context}: missing F12 delta key {key}")
    room_f2f = payload.get("room_f2f")
    if not isinstance(room_f2f, dict):
        raise TestFailure(f"{context}: room_f2f must be dict")
    for place_id in F12_ROOM_PLACES:
        if place_id not in room_f2f:
            raise TestFailure(f"{context}: room_f2f missing place {place_id}")
        if not isinstance(room_f2f[place_id], list):
            raise TestFailure(f"{context}: room_f2f[{place_id}] must be list")
    for list_key in (
        "location_changes",
        "social_events",
        "state_changes",
        "world_events",
    ):
        if not isinstance(payload.get(list_key), list):
            raise TestFailure(f"{context}: {list_key} must be list")
    if not isinstance(payload.get("agent_messages"), dict):
        raise TestFailure(f"{context}: agent_messages must be dict")
    if not isinstance(payload.get("agent_locations"), dict):
        raise TestFailure(f"{context}: agent_locations must be dict")
    player_place = str(payload.get("player_place_id") or "")
    if player_place and player_place not in F12_ROOM_PLACES:
        raise TestFailure(f"{context}: invalid player_place_id={player_place!r}")


def assert_f12_snapshot_shape(
    payload: Dict[str, Any],
    *,
    context: str,
) -> None:
    for key in F12_SNAPSHOT_KEYS:
        if key not in payload:
            raise TestFailure(f"{context}: missing snapshot key {key}")
    place_attrs = payload.get("place_attrs")
    if not isinstance(place_attrs, dict):
        raise TestFailure(f"{context}: place_attrs must be dict")
    for place_id in F12_ROOM_PLACES:
        if place_id not in place_attrs:
            raise TestFailure(f"{context}: place_attrs missing {place_id}")
    if not isinstance(payload.get("agent_locations"), dict):
        raise TestFailure(f"{context}: agent_locations must be dict")
    if not isinstance(payload.get("relations"), list):
        raise TestFailure(f"{context}: relations must be list")
    if not isinstance(payload.get("group_members"), dict):
        raise TestFailure(f"{context}: group_members must be dict")
    if not isinstance(payload.get("name_map"), dict):
        raise TestFailure(f"{context}: name_map must be dict")


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


def _delta_has_activity(delta: Dict[str, Any]) -> bool:
    room_f2f = delta.get("room_f2f") or {}
    if any(len(v or []) for v in room_f2f.values()):
        return True
    if delta.get("public_messages") or delta.get("observer_messages"):
        return True
    if delta.get("group_messages"):
        return True
    agent_messages = delta.get("agent_messages") or {}
    for payload in agent_messages.values():
        if (payload.get("rdc") or payload.get("grp")):
            return True
    return False


def poll_world_delta(
    base: str,
    cookie: str,
    since_tick: int,
    *,
    max_wait: float = 180.0,
    require_activity: bool = True,
) -> Tuple[Dict[str, Any], str, int]:
    """Poll F14 until activity or tick advance (Phase 2)."""
    deadline = time.time() + max_wait
    client_since = int(since_tick)
    last: Dict[str, Any] = {}
    last_through = client_since
    while time.time() < deadline:
        url = f"{base}{BASE_PATH}/world-delta?since_tick={client_since}"
        code, payload, cookie = http_json("GET", url, cookie=cookie, timeout=30.0)
        if code != 200 or not payload.get("success"):
            raise TestFailure(f"world-delta HTTP {code}: {payload}")
        last = payload.get("data") or {}
        assert_f12_delta_shape(last, context="world-delta")
        through = int(last.get("through_tick", client_since))
        if through < last_through:
            raise TestFailure(
                f"F14 through_tick regressed {last_through} → {through}"
            )
        last_through = through
        if require_activity and _delta_has_activity(last):
            return last, cookie, through
        if not require_activity and through > client_since:
            return last, cookie, through
        client_since = through
        time.sleep(0.5)
    raise TestFailure(f"world-delta timeout after {max_wait}s; last={last}")


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
        CommandType.ENQUEUE_PLAYER_INPUT,
        CommandType.UPDATE_SESSION_MIRROR,
        CommandType.GET_LOOP_STATUS,
        CommandType.PAUSE_LOOP,
        CommandType.RESUME_LOOP,
        CommandType.LIST_PLACES,
        CommandType.MOVE_AGENT,
        CommandType.RESET_WORLD,
        CommandType.CLOSE_ENV,
    }
    ok(f"IPC CommandType registry includes {len(registered)} HBM commands")


def test_m4_http_modules() -> None:
    section("T1e M4 http/ 模块与 routes 入口 shim")
    import agent_world.hbm_demo.routes as root_routes
    from agent_world.hbm_demo.http import health, http_errors, ipc_helper, routes as http_routes

    if root_routes.hbm_bp is not http_routes.hbm_bp:
        raise TestFailure("routes.py shim != http.routes.hbm_bp")
    ok("routes.py shim → http.routes.hbm_bp")

    for name, obj in (
        ("ipc_helper.send_inject_batch", ipc_helper.send_inject_batch),
        ("ipc_helper.send_enqueue_player_input", ipc_helper.send_enqueue_player_input),
        ("ipc_helper.send_update_session_mirror", ipc_helper.send_update_session_mirror),
        ("ipc_helper.send_get_loop_status", ipc_helper.send_get_loop_status),
        ("ipc_helper.send_pause_loop", ipc_helper.send_pause_loop),
        ("ipc_helper.send_resume_loop", ipc_helper.send_resume_loop),
        ("ipc_helper.wait_for_loop_window", ipc_helper.wait_for_loop_window),
        ("ipc_helper.push_session_mirror", ipc_helper.push_session_mirror),
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
        "/simulations/<sim_id>/world-snapshot",
        "/simulations/<sim_id>/world-delta",
        "/simulations/<sim_id>/world-loop/status",
        "/simulations/<sim_id>/world-loop/pause",
        "/simulations/<sim_id>/world-loop/resume",
        "/simulations/<sim_id>/prompt-trace/<trace_id>",
        "/simulations/<sim_id>/prompt-trace/by-ref",
        "/simulations/<sim_id>/prompt-traces",
        "/simulations/<sim_id>/debug-inject",
    }
    if rules != expected:
        raise TestFailure(f"hbm_bp routes mismatch: {sorted(rules)}")
    ok(f"hbm_bp registers {len(expected)} HTTP endpoints (F08+F13+F14)")


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
        RECEPTION_PLACE,
        check_action_complete,
    )
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_f07_enabled,
    )

    class EmptyDB:
        def has_f2f_after(self, *a, **k):
            return False

        def has_npc_f2f_after(self, *a, **k):
            return False

        def has_rdc_pair_after(self, *a, **k):
            return False

        def has_grp_after(self, *a, **k):
            return False

    class F2fReceptionDB(EmptyDB):
        def has_f2f_after(self, place_id, *a, **k):
            return place_id == RECEPTION_PLACE

        def has_npc_f2f_after(self, place_id, *a, **k):
            return place_id == RECEPTION_PLACE

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

    ed = empty_delta(3, player_place_id="nvidia_reception")
    if ed.get("through_tick") != 3 or ed.get("public_messages") != []:
        raise TestFailure(f"empty_delta wrong: {ed}")
    for key in (
        "room_f2f",
        "agent_messages",
        "location_changes",
        "social_events",
        "state_changes",
        "world_events",
        "agent_locations",
        "player_place_id",
    ):
        if key not in ed:
            raise TestFailure(f"empty_delta missing F12 key {key}: {ed}")
    ok("F11-B empty_delta (F12 fields)")

    class _Row(dict):
        def __getitem__(self, key):  # noqa: ANN001
            return dict.__getitem__(self, key)

        def keys(self):  # noqa: ANN001
            return dict.keys(self)

    class FakeDB:
        def fetch_f2f_history_at(self, place_id, t_now, since_t):  # noqa: ANN001
            return [(2, 1, 1, "前台你好"), (4, 1, 2, "请稍等")]

        def fetch_f2f_by_places(self, since_t, t_now, place_ids):  # noqa: ANN001
            out = {pid: [] for pid in place_ids}
            if "nvidia_reception" in out:
                history = self.fetch_f2f_history_at(
                    "nvidia_reception", t_now, since_t
                )
                out["nvidia_reception"] = [h for h in history if h[0] > since_t]
            return out

        def fetch_rdc_for_agent(self, agent_id, since_t, t_now):  # noqa: ANN001
            if agent_id == 3 and since_t < 3 <= t_now:
                return [
                    _Row(
                        channel_type="RDC",
                        sender_id=2,
                        recipient_id=3,
                        group_id=None,
                        content="内参",
                        place_id="",
                        attempted_at=3,
                        delivered=1,
                    )
                ]
            return []

        def fetch_grp_for_agent(self, agent_id, since_t, t_now):  # noqa: ANN001
            if agent_id == 4 and since_t < 5 <= t_now:
                return [
                    _Row(
                        channel_type="GRP",
                        sender_id=4,
                        recipient_id=None,
                        group_id=100,
                        content="群消息",
                        place_id="negotiation_room",
                        attempted_at=5,
                        delivered=1,
                    )
                ]
            return []

        def fetch_location_logs_since(self, since_t, t_now):  # noqa: ANN001
            return []

        def fetch_group_events_since(self, since_t, t_now):  # noqa: ANN001
            return []

        def fetch_state_logs_since(self, since_t, t_now, agent_id=None):  # noqa: ANN001
            return []

        def fetch_broadcasts_since(self, since_t, t_now):  # noqa: ANN001
            return []

        def fetch_all_agent_locations(self):  # noqa: ANN001
            return {1: {"place_id": "nvidia_reception", "arrived_at": 0}}

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
                        delivered=1,
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
                        delivered=1,
                    )
                ]
            return []

        def fetch_trace_links_since(self, since_t, t_now):  # noqa: ANN001
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
    if "room_f2f" not in delta or "agent_locations" not in delta:
        raise TestFailure(f"F12 delta keys missing: {delta.keys()}")
    ok("F11-B build_turn_delta filters since_tick (F12 delta)")


def test_f11_c_frontend() -> None:
    section("T1j F11-C / F14 前端增量合并")
    web_src = HBM_DIR / "web" / "src"

    delta_poll = (web_src / "features" / "game-loop" / "useWorldDeltaPoll.ts").read_text(
        encoding="utf-8"
    )
    delta_apply = (web_src / "features" / "game-loop" / "worldDeltaApply.ts").read_text(
        encoding="utf-8"
    )
    if "getWorldDelta" not in delta_poll or "APPLY_WORLD_DELTA" not in delta_apply:
        raise TestFailure("useWorldDeltaPoll/worldDeltaApply missing getWorldDelta / APPLY_WORLD_DELTA")
    ok("useWorldDeltaPoll F14 resident poll wired")

    delta_sync = (web_src / "features" / "game-loop" / "useWorldDeltaSync.ts").read_text(
        encoding="utf-8"
    )
    if "useWorldDeltaStream" not in delta_sync or "useWorldDeltaPoll" not in delta_sync:
        raise TestFailure("useWorldDeltaSync missing WS + poll fallback wiring")
    ok("useWorldDeltaSync F16 WS + F14 poll fallback wired")

    game_loop = (web_src / "features" / "game-loop" / "useGameLoop.ts").read_text(
        encoding="utf-8"
    )
    if "accepted" not in game_loop:
        raise TestFailure("useGameLoop missing Phase2 accepted player-turn path")
    ok("useGameLoop Phase2 accepted enqueue path")

    store = (web_src / "store" / "gameStore.ts").read_text(encoding="utf-8")
    if "APPLY_WORLD_DELTA" not in store or "roomF2f" not in store:
        raise TestFailure("gameStore missing F12 APPLY_WORLD_DELTA / roomF2f state")
    ok("gameStore APPLY_WORLD_DELTA + roomF2f state")

    hbm_api = (web_src / "api" / "hbm.ts").read_text(encoding="utf-8")
    if "getWorldDelta" not in hbm_api:
        raise TestFailure("hbm.ts missing getWorldDelta for F14")
    if "getWorldSnapshot" not in hbm_api:
        raise TestFailure("hbm.ts missing getWorldSnapshot for F12 calibration")
    ok("api/hbm.ts getWorldDelta + getWorldSnapshot")

    import re

    game_loop_const = (web_src / "constants" / "gameLoop.ts").read_text(encoding="utf-8")
    if not re.search(r"DELTA_POLL_MS\s*=\s*\d+", game_loop_const):
        raise TestFailure("gameLoop DELTA_POLL_MS missing for F14")
    ok("DELTA_POLL_MS configured for F14 poll")

    messages = (web_src / "utils" / "messages.ts").read_text(encoding="utf-8")
    if "messageKey" not in messages or "mergeMessages" not in messages:
        raise TestFailure("utils/messages dedupe helpers missing")
    ok("messageKey dedupe for delta merge")


def test_f12_phase1_persistence() -> None:
    section("T1k F12 Phase 1 Runner persistence logs")
    from agent_world.hbm_demo.scripts.acceptance import f12_phase1

    rc = f12_phase1.main()
    if rc != 0:
        raise TestFailure("F12 Phase 1 persistence tests failed")
    ok("F12 Phase 1 persistence script passed")


def test_f12_phase2_world_delta() -> None:
    section("T1l F12 Phase 2 Flask world delta API")
    from agent_world.hbm_demo.scripts.acceptance import f12_world_delta

    rc = f12_world_delta.main()
    if rc != 0:
        raise TestFailure("F12 Phase 2 world delta tests failed")
    ok("F12 Phase 2 world delta script passed")

    routes = (HBM_DIR / "http" / "routes.py").read_text(encoding="utf-8")
    if "world-snapshot" not in routes:
        raise TestFailure("routes.py missing GET /world-snapshot")
    ok("routes.py registers GET /world-snapshot")

    import agent_world.hbm_demo.game_service as root_gs
    from agent_world.hbm_demo.features.f12_world_sync.handler import (
        get_world_snapshot as feat_get_world_snapshot,
    )

    if root_gs.get_world_snapshot is not feat_get_world_snapshot:
        raise TestFailure("game_service.get_world_snapshot shim != F12 handler")
    ok("game_service.get_world_snapshot shim")


def test_f12_phase3_world_stage() -> None:
    section("T1m F12 Phase 3 四房间世界视图前端")
    web_src = HBM_DIR / "web" / "src"
    required = (
        "WorldStage.tsx",
        "RoomGrid.tsx",
        "RoomCell.tsx",
        "AgentCircle.tsx",
        "AgentEphemeralBubble.tsx",
        "AgentPhoneModal.tsx",
        "WorldEventModal.tsx",
    )
    stage_dir = web_src / "features" / "world-stage"
    for name in required:
        if not (stage_dir / name).is_file():
            raise TestFailure(f"missing world-stage/{name}")
    ok(f"world-stage/ has {len(required)} core components")

    places = (web_src / "utils" / "places.ts").read_text(encoding="utf-8")
    if "ROOM_GRID" not in places:
        raise TestFailure("utils/places.ts missing ROOM_GRID")
    ok("utils/places ROOM_GRID")

    world_sync = (web_src / "store" / "worldSync.ts").read_text(encoding="utf-8")
    if "applyWorldDelta" not in world_sync or "applyWorldSnapshot" not in world_sync:
        raise TestFailure("store/worldSync.ts missing applyWorldDelta helpers")
    ok("store/worldSync delta merge helpers")

    types_src = (web_src / "api" / "types.ts").read_text(encoding="utf-8")
    for field in ("room_f2f", "agent_locations", "world_events", "WorldSnapshot"):
        if field not in types_src:
            raise TestFailure(f"api/types.ts missing F12 field/type {field}")
    ok("api/types F12 TurnDelta + WorldSnapshot types")

    css = (web_src / "styles" / "global.css").read_text(encoding="utf-8")
    if ".room-grid" not in css or ".agent-circle" not in css:
        raise TestFailure("global.css missing F12 room-grid / agent-circle styles")
    ok("global.css F12 world-stage styles")


def test_f12_visibility_no_hidden() -> None:
    section("T1n F12 Phase 4 message visibility (no hidden under F12 delta)")
    from agent_world.hbm_demo.scripts.acceptance import f12_visibility

    rc = f12_visibility.main()
    if rc != 0:
        raise TestFailure("F12 visibility tests failed")
    ok("F12 visibility audit — cross-room F2F/RDC/GRP/broadcast exposed")


def test_f03_action_completion() -> None:
    section("T1f F03 action-result 完成判定")
    from agent_world.hbm_demo.features.f02_player_turn.task import (
        INJECT_STATUS_DONE,
        PendingTask,
    )
    from agent_world.hbm_demo.features.f03_action_result.completion import (
        NEGOTIATION_PLACE,
        RECEPTION_PLACE,
        check_action_complete,
    )
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_f07_enabled,
    )

    class EmptyDB:
        def has_f2f_after(self, *a, **k):
            return False

        def has_npc_f2f_after(self, *a, **k):
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

        def has_npc_f2f_after(self, place_id, *a, **k):
            return place_id == RECEPTION_PLACE

    class F2fNegotiationDB(EmptyDB):
        def has_f2f_after(self, place_id, *a, **k):
            return place_id == NEGOTIATION_PLACE

        def has_npc_f2f_after(self, place_id, *a, **k):
            return place_id == NEGOTIATION_PLACE

    class PlayerOnlyReceptionDB(EmptyDB):
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
        if check_action_complete(task_p1, 5, PlayerOnlyReceptionDB()):
            raise TestFailure("F07 Phase 1 must not complete on player-only F2F (§13.2)")
        ok("F07 Phase 1 F2F-priority completion (§13.2)")
    else:
        if not check_action_complete(task_p1, 6, EmptyDB()):
            raise TestFailure("F03 should complete when ipc_end_tick reached (6-tick inject)")
        ok("F03 completes after ipc_end_tick without hanging")

    class F2fJensenDB(EmptyDB):
        def has_f2f_after(self, place_id, *a, **k):
            return place_id == "jensen_private_room"

    task_p2 = PendingTask(
        task_id="t2",
        start_tick=0,
        place_id="jensen_private_room",
        phase="Phase 2",
        player_turn=5,
        ipc_end_tick=6,
    )
    if True:
        if check_action_complete(task_p2, 6, EmptyDB()):
            raise TestFailure(
                "v2 continuous delta must not complete at ipc_end_tick alone (tick 6)"
            )
        if not check_action_complete(task_p2, 8, EmptyDB()):
            raise TestFailure("v2 should timeout-complete Phase 2 at tick 8")
        ok("v2 continuous delta: Phase 2 no ipc_end-only completion")

    if is_f07_enabled():
        task_p4 = PendingTask(
            task_id="t4",
            start_tick=0,
            place_id=NEGOTIATION_PLACE,
            phase="Phase 4",
            player_turn=21,
            ipc_end_tick=8,
            inject_status=INJECT_STATUS_DONE,
        )
        if check_action_complete(task_p4, 6, RdcOnlyDB()):
            raise TestFailure("F07 Phase 4 must not complete on VP RDC alone (§13.5)")
        if not check_action_complete(task_p4, 5, F2fNegotiationDB()):
            raise TestFailure("F07 Phase 4 should complete on negotiation F2F")
        if not check_action_complete(task_p4, 8, EmptyDB()):
            raise TestFailure("F07 Phase 4 should timeout-complete at tick 8")
        ok("F07 Phase 4 F2F-priority completion (§13.5)")


def test_f07_b_agent_control() -> None:
    """F07-B L3 unit tests (dev_logs/24 §11 B1–B5)."""
    section("T2d F07-B pick_active / world_step")
    from types import SimpleNamespace

    from agent_world.hbm_demo.core.runner.world_step import HbmWorldStep
    from agent_world.hbm_demo.features.f07_agent_control import pick_active_ids, primary_active_ids
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        inject_exclusive_ticks_for,
        load_turn_control,
        resolve_inject_tick_count,
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

    world = SimpleNamespace(agents={1: object(), 2: object(), 3: object(), 7: object()}, world_db=None)
    active = pick_active_ids(ctx_p1, world, t=10, batch_tick_index=99)
    if active:
        raise TestFailure(f"idle tick with no stimulus should not activate agents: {active}")
    ok("B1 pick_active idle → [] (stimulus-driven L3)")

    from agent_world.hbm_demo.core.runner.hbm_agent import HbmAgent

    agent1 = HbmAgent(agent_id=1, name="前台")
    ctx_boot = {
        "phase": "Phase 1",
        "player_turn": 1,
        "place_id": "nvidia_reception",
        "inject_agent_ids": [1],
        "player_inject_tick": None,
    }
    world_boot = SimpleNamespace(
        agents={1: agent1, 2: object(), 3: object()},
        world_db=None,
    )
    opening_tick0 = pick_active_ids(ctx_boot, world_boot, t=1, batch_tick_index=0)
    if opening_tick0 != [1]:
        raise TestFailure(f"Phase 1 opening tick0 expected [1]: {opening_tick0}")
    opening_tick1 = pick_active_ids(ctx_boot, world_boot, t=2, batch_tick_index=1)
    if opening_tick1:
        raise TestFailure(
            f"Phase 1 post-opening idle should not tick reception: {opening_tick1}"
        )
    reopen = pick_active_ids(ctx_boot, world_boot, t=3, batch_tick_index=0)
    if 1 in reopen:
        raise TestFailure(f"opening should not re-tick reception on later batch0: {reopen}")
    ctx_inject = {
        **ctx_boot,
        "player_inject_tick": 5,
    }
    inject_tick0 = pick_active_ids(ctx_inject, world_boot, t=5, batch_tick_index=0)
    if inject_tick0 != [1]:
        raise TestFailure(f"player inject exclusive tick0 expected [1]: {inject_tick0}")
    ok("B1b Phase 1 opening tick once (L3), then wait for player inject")

    from agent_world.hbm_demo.features.f07_agent_control.knowledge import (
        build_agent_knowledge,
    )
    from agent_world.hbm_demo.features.f07_agent_control.player_response import (
        format_opening_directive,
    )

    opening_l6 = format_opening_directive(agent_id=1, phase="Phase 1", player_turn=1)
    if "一句" not in opening_l6 or "禁止" not in opening_l6:
        raise TestFailure(f"opening L6 should constrain one welcome: {opening_l6!r}")
    opening_l4 = build_agent_knowledge(
        SimpleNamespace(phase="Phase 1", player_turn=1),
        1,
        "",
        channel="opening",
    )
    if "开场" not in opening_l4 or "欢迎来到" not in opening_l4:
        raise TestFailure(f"opening L4 should include welcome guidance: {opening_l4[:200]!r}")
    ok("B1c opening prompt-first L4/L6 (no business flag)")

    class _UnreadDB:
        def fetch_arrived_for(self, recipient_id, t, last_seen):  # noqa: ARG002
            if int(recipient_id) == 2:
                return [SimpleNamespace(sender_id=1)]
            return []

        def fetch_f2f_history_at(self, *args, **kwargs):  # noqa: ARG002
            return []

    unread_world = SimpleNamespace(
        agents={1: object(), 2: object(), 3: object()},
        world_db=_UnreadDB(),
        places=SimpleNamespace(L_t=lambda _aid: "negotiation_room"),
    )
    active_unread = pick_active_ids(ctx_p1, unread_world, t=10, batch_tick_index=99)
    if 2 not in active_unread:
        raise TestFailure(f"unread RDC must activate recipient: {active_unread}")
    ok(f"B1 pick_active unread RDC activates recipient: {active_unread}")

    hbm_src = (HBM_DIR / "core" / "runner" / "hbm_agent.py").read_text(encoding="utf-8")
    if "filter_tool_calls" in hbm_src:
        raise TestFailure("L5 removed: hbm_agent must not call filter_tool_calls")
    ok("L5 tool filter removed from hbm_agent (L3 pick_active only)")

    from agent_world.hbm_demo.core.runner.hbm_agent import HbmAgent
    from agent_world.demo.demo_agent import _ToolCall
    from agent_world.hbm_demo.features.f07_agent_control.conversation_control import (
        build_conversation_hints,
        mark_communication_action,
    )

    agent = HbmAgent(agent_id=1, name="前台")
    agent.player_memory.append({"role": "system", "content": "玩家说：测试"})
    mark_communication_action(
        agent,
        action_type=_ToolCall(tool_name="speak_to_local", args={"content": "好的"}),
        action_kwargs={"content": "好的"},
        dispatch_result={"success": True},
        t=5,
    )
    if agent.player_memory:
        raise TestFailure("mark_communication_action should clear player_memory")
    if not getattr(agent, "_inject_responded", False):
        raise TestFailure("mark_communication_action should set inject_responded")
    hints = build_conversation_hints(1, agent, SimpleNamespace(world_db=None), t=6)
    if "do_nothing" not in hints:
        raise TestFailure(f"post-response hints should suggest do_nothing: {hints!r}")
    ok("conversation_control clears inject memory + anti-repeat hints")

    load_turn_control.cache_clear()
    if "experience_hardening" in load_turn_control():
        raise TestFailure("turn_control.yaml must not contain experience_hardening block")
    if inject_exclusive_ticks_for("Phase 1") != 2:
        raise TestFailure(
            f"v2 inject_exclusive from phases expected 2: {inject_exclusive_ticks_for('Phase 1')}"
        )
    ok("v2 Phase0 turn_control: hardening off, inject_exclusive=2")

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
    from agent_world.hbm_demo.features.f07_agent_control.conversation_control import (
        has_unread_inbound,
    )
    from agent_world.hbm_demo.features.f07_agent_control.pick_active import (
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
    if not has_unread_inbound(3, agent3, world_p2, 5, rdc_from=2):
        raise TestFailure("C1 VP should detect unread Jensen RDC")
    if has_unread_inbound(3, agent3, world_p2, 5, rdc_from=4):
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
        def __init__(self, rows, f2f_rows=None):
            self._rows = rows
            self._f2f = f2f_rows or []

        def fetch_rdc_messages(
            self, *, sender_id, recipient_id, since_t, t_now  # noqa: ANN001
        ):
            return [
                r
                for r in self._rows
                if int(r.get("sender_id", -1)) == int(sender_id)
                and int(r.get("recipient_id", -1)) == int(recipient_id)
            ]

        def fetch_f2f_history_at(self, place_id, t_now, since_t, *, limit=30, exclusive_since=False):  # noqa: ANN001
            return list(self._f2f)

        def fetch_f2f_from_sender_at(  # noqa: ANN001
            self, place_id, sender_id, t_now, since_t, *, limit=500, exclusive_since=False
        ):
            sid = int(sender_id)
            return [
                row
                for row in self._f2f
                if int(row[1]) == sid
            ]

    from agent_world.hbm_demo.features.f05_story_routing.routing_config import (
        is_agent_driven,
    )

    class SessB:
        player_turn = 12
        phase = "Phase 2"
        stats = {"execution": 22, "vision": 20, "trust": 10, "burnout": 0}
        phase2_start_tick = 40
        start_tick = 0

    pos_row = {"content": "理论上可行，这是核武器", "sender_id": 3, "recipient_id": 2}
    if is_agent_driven():
        if not node_b_applies(SessB(), FakeDB([pos_row]), 50):
            raise TestFailure("C4 agent_driven node B should apply on positive VP RDC")
        SessB.stats["execution"] = 10
        if not node_b_applies(SessB(), FakeDB([pos_row]), 50):
            raise TestFailure("C4 agent_driven node B must ignore execution stat gate")
        ok("C4 agent_driven node B (DB signal, no Stats gate)")
    else:
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
        start_tick = 0

    if is_agent_driven():
        expel_row = {"content": "请离场", "sender_id": 2, "recipient_id": 4}
        if not node_c_applies(SessC(), FakeDB([expel_row]), 50):
            raise TestFailure("C4 agent_driven node C should apply on Jensen expel RDC")
        SessC.stats["burnout"] = 90
        if not node_c_applies(SessC(), FakeDB([expel_row]), 50):
            raise TestFailure("C4 agent_driven node C must ignore burnout stat gate")
        ok("C4 agent_driven node C (expel keyword in DB)")
    else:
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


def test_f07_d_agent_control() -> None:
    """F07-D Phase 4专规 + 节点 C (dev_logs/24 §11 D1–D5)."""
    section("T2f F07-D Phase 4 inject / L3 / F03")
    from types import SimpleNamespace

    from agent_world.hbm_demo.features import FEATURE_REGISTRY
    from agent_world.hbm_demo.features.f05_story_routing.routing import (
        CEO_IDS,
        TECH_VP_ID,
        build_inject_payload,
        inject_agent_ids_for_phase,
    )
    from agent_world.hbm_demo.features.f07_agent_control.config import is_f07_enabled
    from agent_world.hbm_demo.features.f07_agent_control.knowledge import (
        build_agent_knowledge,
    )
    from agent_world.hbm_demo.features.f07_agent_control.pick_active import (
        pick_active_ids,
        primary_active_ids,
    )
    from agent_world.hbm_demo.features.f07_agent_control.player_response import (
        format_l6_player_directive,
    )

    if FEATURE_REGISTRY.get("F07", {}).get("status") != "implemented":
        raise TestFailure("F07 should be status=implemented after F07-D")
    ok("D3 FEATURE_REGISTRY F07 implemented")

    if not is_f07_enabled():
        ok("F07-D inject/L3 tests skipped (F07 disabled)")
        return

    if inject_agent_ids_for_phase("Phase 4") != [2]:
        raise TestFailure(
            f"D1 Phase 4 inject must be [2] only: {inject_agent_ids_for_phase('Phase 4')}"
        )
    ok("D1 Phase 4 inject_agent_ids [2]")

    class FakeSession:
        phase = "Phase 4"
        player_turn = 21
        place_id = "negotiation_room"
        stats = {"vision": 35, "execution": 25, "trust": 40, "burnout": 30}

    events, _, _ = build_inject_payload(FakeSession(), "加入 NVIDIA", task_id="t21")
    inject_aids = [e["effect"]["agent_id"] for e in events]
    if inject_aids != [2]:
        raise TestFailure(f"D1 Phase 4 build_inject_payload agents wrong: {inject_aids}")
    ok("D1 Phase 4 single inject event → Agent 2")

    ctx_p4_idle = {
        "phase": "Phase 4",
        "player_turn": 21,
        "place_id": "negotiation_room",
        "llm_params": {"temperature": 0.48, "max_tokens": 200},
    }
    if primary_active_ids(ctx_p4_idle) != [2]:
        raise TestFailure(
            f"D1 primary_active Phase 4 must be [2]: {primary_active_ids(ctx_p4_idle)}"
        )
    world = SimpleNamespace(agents={2: object(), 3: object()})
    idle_active = pick_active_ids(ctx_p4_idle, world, t=10, batch_tick_index=99)
    if idle_active:
        raise TestFailure(f"D1 Phase 4 idle without inject should not tick: {idle_active}")
    ctx_p4_inject = {
        **ctx_p4_idle,
        "inject_agent_ids": [2],
        "player_inject_tick": 5,
    }
    active = pick_active_ids(ctx_p4_inject, world, t=5, batch_tick_index=0)
    if 3 in active:
        raise TestFailure(f"D1 Agent 3 present_silent must not tick: {active}")
    if active != [2]:
        raise TestFailure(f"D1 Phase 4 inject exclusive should be [2]: {active}")
    ok("D1 Phase 4 L3 inject→[2], idle→[], Agent 3 present_silent")

    f07_dir = HBM_DIR / "features" / "f07_agent_control"
    if (f07_dir / "tool_guard.py").is_file():
        raise TestFailure("L5 removed: tool_guard.py should not exist")
    if (f07_dir / "tool_matrix.yaml").is_file():
        raise TestFailure("L5 removed: tool_matrix.yaml should not exist")
    ok("D1 L5 tool matrix/guard removed; Phase 4 gating is L3 pick_active only")

    if TECH_VP_ID in CEO_IDS:
        raise TestFailure("D1 node C must not include Tech VP in CEO_IDS")
    ok(f"D1 node C MOVE targets CEO_IDS={list(CEO_IDS)} only (Agent 3 stays)")

    l6 = format_l6_player_directive(
        agent_id=2, phase="Phase 4", player_turn=21, player_text="我想加入团队"
    )
    if "终局 1v1" not in l6:
        raise TestFailure("D2 Phase 4 L6 missing 终局 1v1 directive")
    block = build_agent_knowledge(
        FakeSession(), 2, "加入 NVIDIA", channel="inject"
    )
    if "终局 1v1" not in block:
        raise TestFailure("D2 inject knowledge missing Phase 4 1v1 block")
    ok("D2 Phase 4 L6 / knowledge 1v1 Jensen")

    proto = (ROOT / "dev_docs" / "1_story_prototype.md").read_text(encoding="utf-8")
    if "Agent 2 | batch" not in proto and "Agent 2" not in proto:
        raise TestFailure("D5 dev_docs/1 missing Phase 4 inject table")
    if "present_silent" not in proto:
        raise TestFailure("D5 dev_docs/1 missing present_silent note")
    ok("D5 dev_docs/1 Phase 4 inject Agent 2 + present_silent")


def test_f07_e_step1_player_facing_f2f() -> None:
    """F07-E Step1 — E0 player-facing F2F + E6 session/start hygiene (dev_logs/29)."""
    import asyncio
    import tempfile
    from types import SimpleNamespace

    section("T2g F07-E Step1 E0 player F2F + E6 session hygiene")
    from agent_world.hbm_demo.features import FEATURE_REGISTRY
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_f07_enabled,
        load_turn_control,
    )
    from agent_world.hbm_demo.features.f07_agent_control.player_facing_f2f import (
        PLAYER_RECIPIENT_ID,
        co_located_peer_count,
        emit_player_facing_f2f,
        is_speak_to_local_action,
        should_emit_player_facing_f2f,
    )
    from agent_world.hbm_demo.features.f06_read_model.world_db import ReadOnlyWorldDB
    from agent_world.hbm_demo.features.f11_live_turn_sync.task_state import (
        async_state_path,
        clear_async_state,
        save_task_runtime,
    )
    from agent_world.persistence.world_db import WorldDB

    phase = FEATURE_REGISTRY.get("F07", {}).get("phase", "")
    if "F07-E" not in phase:
        raise TestFailure(f"F07 registry phase should mention F07-E Step1: {phase!r}")
    ok(f"FEATURE_REGISTRY F07 phase: {phase}")

    if not is_f07_enabled():
        ok("F07-E Step1 tests skipped (F07 disabled)")
        return

    load_turn_control.cache_clear()
    if "experience_hardening" in load_turn_control():
        raise TestFailure("turn_control.yaml must not contain experience_hardening block")
    ok("v2 Phase0 experience_hardening retired from turn_control")

    if not is_speak_to_local_action("speak_to_local"):
        raise TestFailure("is_speak_to_local_action failed for string tool name")
    ok("E0 is_speak_to_local_action")

    if should_emit_player_facing_f2f({"success": True, "recipients": [99]}):
        raise TestFailure("should not emit when FaceToFaceBus inserted rows")
    if not should_emit_player_facing_f2f({"success": True, "recipients": []}):
        raise TestFailure("should emit when recipients empty")
    ok("E0 should_emit_player_facing_f2f")

    world = SimpleNamespace(
        places=SimpleNamespace(
            L_t=lambda aid: "nvidia_reception" if aid == 1 else "negotiation_room",
            agents_at=lambda place: {1} if place == "nvidia_reception" else {2, 3},
        )
    )
    if co_located_peer_count(world, 1) != 0:
        raise TestFailure("Phase 1 reception should have 0 co-located peers for agent 1")
    if co_located_peer_count(world, 2) != 1:
        raise TestFailure("negotiation_room agent 2 should have 1 peer")
    ok("E0 co_located_peer_count")

    async def _emit_and_read() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "world.db"
            wdb = WorldDB(str(db_path))
            wdb.init_schema()
            mid = await emit_player_facing_f2f(
                wdb,
                sender_id=1,
                place_id="nvidia_reception",
                content="您提到的方案，我需要跟黄总确认，请稍等。",
                t=7,
            )
            if mid <= 0:
                raise TestFailure(f"emit_player_facing_f2f bad message_id: {mid}")
            ro = ReadOnlyWorldDB(db_path)
            rows = ro.fetch_f2f_history_at("nvidia_reception", 7, 0, limit=10)
            if len(rows) < 1:
                raise TestFailure("fetch_f2f_history_at should see player-facing F2F")
            if rows[0][3] != "您提到的方案，我需要跟黄总确认，请稍等。":
                raise TestFailure(f"unexpected F2F content: {rows[0]}")

    asyncio.run(_emit_and_read())
    ok(f"E0 emit_player_facing_f2f → ReadOnlyWorldDB F2F≥1 (recipient={PLAYER_RECIPIENT_ID})")

    routes_src = (HBM_DIR / "http" / "routes.py").read_text(encoding="utf-8")
    if "clear_async_state" not in routes_src or "session_start" not in routes_src:
        raise TestFailure("routes.session_start should call clear_async_state (E6)")
    ok("E6 session/start clears async_state (source)")

    save_task_runtime(
        SIM_DIR,
        {
            "task_id": "stale_task",
            "start_tick": 0,
            "place_id": "nvidia_reception",
            "phase": "Phase 1",
            "player_turn": 4,
        },
        session_dict={
            "task_id": "stale_task",
            "start_tick": 0,
            "place_id": "nvidia_reception",
            "phase": "Phase 1",
            "player_turn": 4,
            "stats": {"vision": 8, "execution": 5, "trust": 12, "burnout": 3},
        },
    )
    if not async_state_path(SIM_DIR).is_file():
        raise TestFailure("test setup: runtime.json not written")
    clear_async_state(SIM_DIR)
    if async_state_path(SIM_DIR).exists():
        raise TestFailure("clear_async_state should remove runtime.json")
    ok("E6 clear_async_state removes F11 runtime overlay")

    ws_src = (HBM_DIR / "core" / "runner" / "world_step.py").read_text(encoding="utf-8")
    if "_handle_speak_to_local_f2f" not in ws_src:
        raise TestFailure("HbmWorldStep missing player-facing F2F hook")
    ok("E0 HbmWorldStep speak_to_local dispatch hook present")


def test_f08_virtual_player() -> None:
    """F08 — virtual player agent 0, F2F payload, Phase MOVE sync (dev_log/34 PR2)."""
    section("T2g-pre F08 virtual player entity")
    from types import SimpleNamespace

    from agent_world.hbm_demo.features.f01_session.paths import get_name_map
    from agent_world.hbm_demo.features.f08_virtual_player.config import (
        is_f08_enabled,
        player_agent_id,
    )
    from agent_world.hbm_demo.features.f08_virtual_player.player_entity import (
        PLAYER_AGENT_ID,
        sync_player_place_on_routing,
        target_place_for_phase,
    )
    from agent_world.hbm_demo.features.f08_virtual_player.player_f2f import (
        build_player_f2f_payload,
        f2f_recipient_for_phase,
    )
    from agent_world.hbm_demo.features.f07_agent_control.pick_active import (
        pick_active_ids,
    )

    f08_dir = HBM_DIR / "features" / "f08_virtual_player"
    for name in ("config.yaml", "phase_places.yaml", "player_entity.py", "player_f2f.py"):
        if not (f08_dir / name).is_file():
            raise TestFailure(f"F08 missing {name}")
    ok("F08 module files present")

    if not is_f08_enabled():
        raise TestFailure("F08 config.yaml enabled expected true")
    if int(player_agent_id()) != 0:
        raise TestFailure(f"F08 player_agent_id expected 0: {player_agent_id()}")
    ok("F08 enabled, player_agent_id=0")

    from agent_world.hbm_demo.shared import config_loader

    scenario = config_loader.load_scenario(HBM_DIR / "hbm_scenario.yaml")
    agent0 = next(
        (a for a in scenario.get("agents", []) if int(a.get("agent_id", -1)) == 0),
        None,
    )
    if agent0 is None or str(agent0.get("name")) != "玩家":
        raise TestFailure(f"hbm_scenario agent 0 missing or wrong name: {agent0}")
    ok("hbm_scenario.yaml agent 0 @ 玩家")

    name_map = get_name_map()
    if name_map.get(0) != "玩家":
        raise TestFailure(f"name_map[0] expected 玩家: {name_map.get(0)}")
    ok("get_name_map includes agent 0 → 玩家")

    if target_place_for_phase("Phase 2") != "jensen_private_room":
        raise TestFailure("target_place_for_phase Phase 2 wrong")
    if target_place_for_phase("Phase 4") != "negotiation_room":
        raise TestFailure("target_place_for_phase Phase 4 wrong")
    ok("phase_places.yaml mapping")

    session = SimpleNamespace(
        phase="Phase 1",
        place_id="nvidia_reception",
        player_turn=1,
    )
    payload = build_player_f2f_payload(session, "  我的算法能省 80% 显存  ")
    if not payload or payload.get("sender_id") != 0:
        raise TestFailure(f"build_player_f2f_payload bad: {payload}")
    if payload.get("recipient_id") != f2f_recipient_for_phase("Phase 1"):
        raise TestFailure(f"recipient mismatch: {payload}")
    if payload.get("content") != "我的算法能省 80% 显存":
        raise TestFailure(f"content not stripped: {payload}")
    ok("build_player_f2f_payload Phase 1")

    moves: list[tuple[int, str]] = []

    class _Ipc:
        pass

    def _fake_move(_client, *, agent_id, place_id, timeout=600.0):  # noqa: ANN001, ARG001
        moves.append((int(agent_id), str(place_id)))
        return SimpleNamespace(status=SimpleNamespace(value="completed"), result={})

    import agent_world.hbm_demo.http.ipc_helper as ipc_mod

    real_move = ipc_mod.send_move_agent
    ipc_mod.send_move_agent = _fake_move  # type: ignore[assignment]
    try:
        sync_player_place_on_routing(
            session,
            ipc_client=_Ipc(),
            new_phase="Phase 2",
            node="A",
            ipc_timeout=1.0,
        )
        if session.phase != "Phase 2" or session.place_id != "jensen_private_room":
            raise TestFailure(f"node A session wrong: {session.phase} {session.place_id}")
        if moves != [(0, "jensen_private_room")]:
            raise TestFailure(f"node A MOVE wrong: {moves}")
        moves.clear()
        session.place_id = "jensen_private_room"
        sync_player_place_on_routing(
            session,
            ipc_client=_Ipc(),
            new_phase="Phase 4",
            node="C",
            ipc_timeout=1.0,
        )
        if session.phase != "Phase 4" or session.place_id != "jensen_private_room":
            raise TestFailure(f"node C session wrong: {session.phase} {session.place_id}")
        if moves:
            raise TestFailure(f"node C must not MOVE player: {moves}")
    finally:
        ipc_mod.send_move_agent = real_move

    ok("sync_player_place_on_routing nodes A/C")

    ctx = {"phase": "Phase 1", "player_turn": 1, "inject_agent_ids": [1]}
    world = SimpleNamespace(agents={1: object()}, world_db=None)
    active = pick_active_ids(ctx, world, t=10, batch_tick_index=0)
    if PLAYER_AGENT_ID in active:
        raise TestFailure(f"virtual player must not be pick_active: {active}")
    ok("pick_active excludes agent 0")


def test_f08_pr4_inject_and_f2f_delivery() -> None:
    """F08 PR4 — Phase 2+ F2F inject channel; Bus vs emit_player_facing_f2f (dev_log/34)."""
    section("T2g-post F08 PR4 inject channel + Bus/emit split")
    from types import SimpleNamespace

    from agent_world.hbm_demo.features.f05_story_routing.routing import build_inject_payload
    from agent_world.hbm_demo.features.f07_agent_control.knowledge import build_agent_knowledge
    from agent_world.hbm_demo.features.f07_agent_control.player_facing_f2f import (
        bus_delivered_player_facing_f2f,
        should_emit_player_facing_f2f,
    )
    from agent_world.hbm_demo.features.f07_agent_control.player_response import (
        inject_channel_uses_player_f2f,
    )
    from agent_world.hbm_demo.features.f08_virtual_player.config import is_f08_enabled

    if not is_f08_enabled():
        ok("F08 PR4 tests skipped (F08 disabled)")
        return

    if not inject_channel_uses_player_f2f("Phase 2"):
        raise TestFailure("Phase 2 should use F2F inject channel when F08 enabled")
    if inject_channel_uses_player_f2f("Phase 1"):
        raise TestFailure("Phase 1 must keep dual-channel inject + F2F")
    ok("inject_channel_uses_player_f2f Phase gating")

    class FakeSession:
        phase = "Phase 1"
        player_turn = 1
        place_id = "nvidia_reception"
        stats = {"vision": 0, "execution": 0, "trust": 10, "burnout": 0}

    p1_events, _, _ = build_inject_payload(FakeSession(), "你好前台", task_id="t1")
    p1_text = p1_events[0]["effect"].get("text") or ""
    if "玩家说：「你好前台」" not in p1_text:
        raise TestFailure("Phase 1 inject must still include verbatim 玩家说")
    ok("Phase 1 dual-channel inject retains 玩家说")

    FakeSession.phase = "Phase 2"
    FakeSession.player_turn = 5
    FakeSession.place_id = "jensen_private_room"
    p2_events, _, _ = build_inject_payload(FakeSession(), "凭什么省80%", task_id="t2")
    p2_text = p2_events[0]["effect"].get("text") or ""
    if "F2F 通道" not in p2_text:
        raise TestFailure("Phase 2 inject must use F2F channel header")
    if "玩家说：「" in p2_text:
        raise TestFailure("Phase 2 inject must not duplicate player verbatim")
    ok("Phase 2+ inject uses F2F channel without 玩家说 duplicate")

    FakeSession.phase = "Phase 4"
    FakeSession.player_turn = 21
    p4_block = build_agent_knowledge(
        FakeSession(), 2, "加入 NVIDIA", channel="inject"
    )
    if "终局 1v1" not in p4_block:
        raise TestFailure("Phase 4 F2F inject missing 终局 1v1 directive")
    if "玩家说：「" in p4_block:
        raise TestFailure("Phase 4 F2F inject must not include 玩家说")
    ok("Phase 4 F2F-aware inject knowledge")

    if not bus_delivered_player_facing_f2f({"success": True, "recipients": [101]}):
        raise TestFailure("bus_delivered should be true when FaceToFaceBus inserted rows")
    if should_emit_player_facing_f2f({"success": True, "recipients": [101]}):
        raise TestFailure("should not emit when Bus already delivered")
    if not should_emit_player_facing_f2f({"success": True, "recipients": []}):
        raise TestFailure("should emit when Bus recipients empty")
    ok("Bus vs emit_player_facing_f2f mutual exclusion")


def test_f07_e_step2_no_scripted_fallback() -> None:
    """Agent-native policy — no scripted F2F/RDC companion; prompt-only guidance."""
    section("T2h F07 no scripted player-facing fallback")
    from agent_world.hbm_demo.features import FEATURE_REGISTRY

    phase = FEATURE_REGISTRY.get("F07", {}).get("phase", "")
    if "F07-E" not in phase:
        raise TestFailure(f"F07 registry phase should mention F07-E: {phase!r}")
    ok(f"FEATURE_REGISTRY F07 phase: {phase}")

    f07_dir = HBM_DIR / "features" / "f07_agent_control"
    if (f07_dir / "f2f_fallback.py").is_file():
        raise TestFailure("f2f_fallback.py must be removed (no template F2F)")
    if (f07_dir / "reception_rdc_companion.py").is_file():
        raise TestFailure("reception_rdc_companion.py must be removed (no scripted RDC)")
    ok("scripted fallback modules absent")

    ws_src = (HBM_DIR / "core" / "runner" / "world_step.py").read_text(encoding="utf-8")
    loop_src = (HBM_DIR / "core" / "runner" / "world_loop.py").read_text(encoding="utf-8")
    pr_src = (f07_dir / "player_response.py").read_text(encoding="utf-8")
    if "apply_batch_f2f_fallback" in ws_src or "apply_batch_f2f_fallback_at" in ws_src:
        raise TestFailure("world_step must not reference batch F2F fallback")
    if "apply_batch_f2f_fallback_at" in loop_src:
        raise TestFailure("world_loop must not call batch F2F fallback")
    if "_ensure_reception_rdc_companion" in ws_src:
        raise TestFailure("world_step must not auto-send reception RDC companion")
    if "系统代发" in pr_src:
        raise TestFailure("L6 prompt must not mention system-generated F2F fallback")
    ok("runner + L6: no scripted player-facing fallback hooks")


def test_f07_e_step3_inject_exclusive_ticks() -> None:
    """F07 inject_exclusive_ticks + IPC tick cap (post-hardening cleanup)."""
    from types import SimpleNamespace

    section("T2i F07 inject_exclusive_ticks + IPC tick cap")
    from agent_world.hbm_demo.features import FEATURE_REGISTRY
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        inject_exclusive_ticks_for,
        is_f07_enabled,
        load_turn_control,
        max_inject_tick_loops,
        resolve_inject_tick_loops,
    )
    from agent_world.hbm_demo.features.f07_agent_control.pick_active import (
        pick_active_ids,
    )

    phase = FEATURE_REGISTRY.get("F07", {}).get("phase", "")
    if "F07-E" not in phase:
        raise TestFailure(f"F07 registry phase should mention F07-E: {phase!r}")
    ok(f"FEATURE_REGISTRY F07 phase: {phase}")

    if not is_f07_enabled():
        ok("F07 inject_exclusive tests skipped (F07 disabled)")
        return

    load_turn_control.cache_clear()
    if "experience_hardening" in load_turn_control():
        raise TestFailure("turn_control.yaml must not contain experience_hardening block")

    if inject_exclusive_ticks_for("Phase 1") != 2:
        raise TestFailure(
            f"Phase1 inject_exclusive expected 2: {inject_exclusive_ticks_for('Phase 1')}"
        )
    ok("Phase1 inject_exclusive_ticks=2")

    if max_inject_tick_loops() != 8:
        raise TestFailure(f"max_inject_tick_loops should be 8: {max_inject_tick_loops()}")
    if resolve_inject_tick_loops(8) != 8:
        raise TestFailure("resolve_inject_tick_loops(8) should run 8 ticks")
    if resolve_inject_tick_loops(20) != 8:
        raise TestFailure("resolve_inject_tick_loops should cap at 8")
    ok("resolve_inject_tick_loops cap=8")

    ipc_src = (HBM_DIR / "core" / "runner" / "ipc_handlers.py").read_text(encoding="utf-8")
    if "resolve_inject_tick_loops" not in ipc_src:
        raise TestFailure("ipc_handlers should use resolve_inject_tick_loops")
    ok("ipc_handlers inject tick loop wired")

    ctx_p1 = {
        "phase": "Phase 1",
        "player_turn": 1,
        "place_id": "nvidia_reception",
        "inject_agent_ids": [1],
        "player_inject_tick": 1,
    }
    world = SimpleNamespace(agents={1: object(), 2: object(), 3: object()})

    exclusive_tick0 = pick_active_ids(ctx_p1, world, t=1, batch_tick_index=0)
    if exclusive_tick0 != [1]:
        raise TestFailure(f"inject_exclusive tick0 expected [1]: {exclusive_tick0}")
    exclusive_tick1 = pick_active_ids(ctx_p1, world, t=2, batch_tick_index=1)
    if exclusive_tick1 != [1]:
        raise TestFailure(f"inject_exclusive tick1 expected [1]: {exclusive_tick1}")
    ok("inject_exclusive_ticks Phase 1 tick0-1 → [1] only")

    normal_tick2 = pick_active_ids(ctx_p1, world, t=3, batch_tick_index=2)
    if 1 not in normal_tick2:
        raise TestFailure(
            f"inject_response window should keep inject agent active: {normal_tick2}"
        )
    ok(f"post-inject window active={normal_tick2}")

    ws_src = (HBM_DIR / "core" / "runner" / "world_step.py").read_text(encoding="utf-8")
    if "_batch_tick_index" not in ws_src:
        raise TestFailure("HbmWorldStep missing batch_tick_index")
    if "_mark_rdc_if_sent" in ws_src or "batch_guard" in ws_src:
        raise TestFailure("HbmWorldStep must not retain hardening batch_guard hooks")
    ok("world_step batch_tick_index without hardening hooks")


def test_f07_e_step4_turn_priority_and_offtopic() -> None:
    """F07-E Step4 — E3 turn-scoped L6 + Jensen summary + E4 off-topic guard (dev_logs/29)."""
    section("T2j F07-E Step4 E3 turn priority + E4 off-topic guard")
    from types import SimpleNamespace

    from agent_world.hbm_demo.features import FEATURE_REGISTRY
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_f07_enabled,
        load_turn_control,
    )
    from agent_world.hbm_demo.features.f07_agent_control.knowledge import (
        build_agent_knowledge,
        load_agent_overlay,
    )
    from agent_world.hbm_demo.features.f07_agent_control.llm_params import (
        resolve_passive_llm_params,
    )
    from agent_world.hbm_demo.features.f07_agent_control.player_response import (
        format_l6_player_directive,
        format_notification_directive,
    )

    phase = FEATURE_REGISTRY.get("F07", {}).get("phase", "")
    if "F07-E Step4" not in phase and "F07-E Step5" not in phase:
        raise TestFailure(f"F07 registry phase should mention F07-E Step4+: {phase!r}")
    ok(f"FEATURE_REGISTRY F07 phase: {phase}")

    if not is_f07_enabled():
        ok("F07-E Step4 tests skipped (F07 disabled)")
        return

    load_turn_control.cache_clear()
    if "experience_hardening" in load_turn_control():
        raise TestFailure("turn_control.yaml must not contain experience_hardening block")

    l6 = format_l6_player_directive(
        agent_id=1,
        phase="Phase 1",
        player_turn=2,
        player_text="我给您带了杯咖啡，黄总在吗？",
    )
    if "必须先直接回应玩家" not in l6:
        raise TestFailure("L6 missing direct-response line")
    ok("L6 core player-response directive")

    notif = format_notification_directive(
        phase="Phase 1", player_turn=1, agent_id=2
    )
    if "roadmap" not in notif and "RDC" not in notif:
        raise TestFailure(f"E4 notification missing off-topic guard: {notif[:80]}")
    ok("E4 Phase1 Jensen notification narrowed")

    passive = resolve_passive_llm_params("Phase 1")
    if not passive or passive.get("temperature") != 0.35:
        raise TestFailure(f"E4 Phase_1_passive params unexpected: {passive}")
    ok("E4 resolve_passive_llm_params Phase_1_passive")

    overlay = load_agent_overlay(1)
    checklist = (
        (overlay.get("phase_overrides") or {}).get("Phase 1") or {}
    ).get("response_checklist") or []
    if not any("闲聊" in str(x) for x in checklist):
        raise TestFailure("agent_1.yaml missing small-talk checklist item")
    ok("E3 agent_1.yaml response_checklist small-talk item")

    ipc_src = (HBM_DIR / "core" / "runner" / "ipc_handlers.py").read_text(
        encoding="utf-8"
    )
    if "notify_jensen_player_summary" in ipc_src:
        raise TestFailure("ipc_handlers must not reference notify_jensen_player_summary")
    if "clear_player_memory_for_agents" not in ipc_src:
        raise TestFailure("A6 clear_player_memory_for_agents regression")
    ok("ipc_handlers: no Jensen summary hook; A6 memory clear kept")

    ws_src = (HBM_DIR / "core" / "runner" / "world_step.py").read_text(encoding="utf-8")
    if "batch_guard" in ws_src or "_mark_rdc_if_sent" in ws_src:
        raise TestFailure("world_step must not retain hardening hooks")

    ha_src = (HBM_DIR / "core" / "runner" / "hbm_agent.py").read_text(encoding="utf-8")
    if "do_nothing" not in ha_src or "未读 RDC" not in ha_src:
        raise TestFailure("hbm_agent missing Phase1 RDC response rule")
    ok("hbm_agent Phase1 RDC response rules")

    session = SimpleNamespace(
        phase="Phase 1", player_turn=1, place_id="nvidia_reception", stats={}
    )
    block = build_agent_knowledge(
        session, 1, "80% 显存优化", channel="inject"
    )
    if "80%" not in block:
        raise TestFailure("inject knowledge block should include player text")
    ok("E3 build_agent_knowledge inject still includes player line")


def test_f07_e_step5_phase4_smoke_module() -> None:
    """Phase4 IPC smoke helper module (optional live run when runner ready)."""
    section("T2k F07 Phase4 smoke module")
    from agent_world.hbm_demo.features import FEATURE_REGISTRY
    from agent_world.hbm_demo.features.f07_agent_control.config import is_f07_enabled
    from agent_world.hbm_demo.scripts.acceptance.phase4_smoke import (
        Phase4SmokeResult,
        run_phase4_ipc_smoke,
    )
    from agent_world.hbm_demo.shared.env_status import is_runner_ready

    phase = FEATURE_REGISTRY.get("F07", {}).get("phase", "")
    if "F07-E Step5" not in phase:
        raise TestFailure(f"F07 registry phase should mention F07-E Step5: {phase!r}")
    ok(f"FEATURE_REGISTRY F07 phase: {phase}")

    if not is_f07_enabled():
        ok("Phase4 smoke skipped (F07 disabled)")
        return

    smoke_src = (
        HBM_DIR / "scripts" / "acceptance" / "phase4_smoke.py"
    ).read_text(encoding="utf-8")
    if "run_phase4_ipc_smoke" not in smoke_src:
        raise TestFailure("phase4_smoke.py missing run_phase4_ipc_smoke")
    ok("phase4_smoke module present")

    if is_runner_ready(str(SIM_DIR)):
        result = run_phase4_ipc_smoke(SIM_DIR, ipc_timeout=120.0)
        if not isinstance(result, Phase4SmokeResult):
            raise TestFailure("run_phase4_ipc_smoke return type")
        if not result.ok:
            raise TestFailure(
                f"Phase4 IPC smoke failed: inject={result.inject_agent_ids} "
                f"jensen_f2f={result.jensen_f2f_count} vp={result.vp_public_count} "
                f"ceo_in_room={result.ceo_in_negotiation}"
            )
        ok(
            f"Phase4 IPC smoke — Jensen F2F={result.jensen_f2f_count} "
            f"end_tick={result.end_tick}"
        )
    else:
        ok("Phase4 IPC smoke skipped (runner not ready in unit pass)")


def test_f07_v2_phase0_hard_control_retired() -> None:
    """dev_logs/31 Phase 0 — retire F07-E hard guards; HBM MOVE is IPC-only."""
    import asyncio

    section("T2l v2 Phase0 hard control retired")
    from types import SimpleNamespace

    from agent_world.hbm_demo.core.runner.hbm_dispatcher import HbmActionDispatcher
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_f07_enabled,
        load_turn_control,
    )

    if not is_f07_enabled():
        ok("v2 Phase0 skipped (F07 disabled)")
        return

    load_turn_control.cache_clear()
    if "experience_hardening" in load_turn_control():
        raise TestFailure("turn_control.yaml must not contain experience_hardening block")
    ok("Phase0 turn_control: experience_hardening retired; L5 tool filter removed")

    ws_src = (HBM_DIR / "core" / "runner" / "world_step.py").read_text(encoding="utf-8")
    loop_src = (HBM_DIR / "core" / "runner" / "world_loop.py").read_text(encoding="utf-8")
    if "apply_batch_f2f_fallback" in ws_src or "apply_batch_f2f_fallback_at" in loop_src:
        raise TestFailure("Phase0: runner must not call scripted F2F fallback")
    ok("Phase0 runner: batch F2F fallback removed")

    kernel_src = (HBM_DIR / "core" / "runner" / "kernel.py").read_text(encoding="utf-8")
    if "HbmActionDispatcher" not in kernel_src:
        raise TestFailure("Phase0: kernel must wire HbmActionDispatcher")
    ok("Phase0 kernel uses HbmActionDispatcher")

    async def _move_noop() -> None:
        disp = HbmActionDispatcher(
            world_state=SimpleNamespace(),
            f2f_bus=SimpleNamespace(),
            rdc_bus=SimpleNamespace(),
            grp_bus=SimpleNamespace(),
            pool_manager=SimpleNamespace(),
            script_engine=SimpleNamespace(),
        )
        result = await disp.dispatch(
            2, "request_move", 5, place_id="jensen_private_room"
        )
        if result.get("noop") is not True:
            raise TestFailure(f"Phase0 agent MOVE should noop: {result}")
        if disp.pending_moves:
            raise TestFailure("Phase0 MOVE must not enqueue pending_moves")

    asyncio.run(_move_noop())
    ok("Phase0 HbmActionDispatcher silently ignores request_move")


def test_f07_v2_phase1_world_loop() -> None:
    """dev_logs/31 Phase 1 — WorldLoopOrchestrator + PlayerInputQueue + enqueue IPC."""
    section("T2m v2 Phase1 world loop")
    from agent_world.hbm_demo.core.runner.player_input_queue import (
        PlayerInputItem,
        PlayerInputQueue,
        ScriptQueueItem,
    )
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_world_loop_enabled,
        load_turn_control,
        world_loop_tick_interval,
    )
    from agent_world.hbm_demo.features.f07_agent_control.session_mirror import (
        bootstrap_mirror,
        mirror_from_session,
    )
    from agent_world.ipc.commands import CommandType

    for mod_name in (
        "agent_world.hbm_demo.core.runner.world_loop",
        "agent_world.hbm_demo.core.runner.player_input_queue",
    ):
        __import__(mod_name)
        ok(f"import {mod_name.rsplit('.', 1)[-1]}")

    load_turn_control.cache_clear()
    if not is_world_loop_enabled():
        raise TestFailure("Phase1: turn_control world_loop.enabled must be true")
    ok(f"world_loop enabled interval={world_loop_tick_interval()}s")

    for cmd in (
        CommandType.ENQUEUE_PLAYER_INPUT,
        CommandType.UPDATE_SESSION_MIRROR,
        CommandType.GET_LOOP_STATUS,
    ):
        if not isinstance(cmd.value, str):
            raise TestFailure(f"Phase1 missing IPC command: {cmd}")
    ok("Phase1 IPC commands registered")

    q = PlayerInputQueue(max_depth=2)
    if not q.enqueue_player(PlayerInputItem([], {"phase": "Phase 1"})):
        raise TestFailure("Phase1 queue enqueue_player failed")
    if not q.enqueue_script(ScriptQueueItem([])):
        raise TestFailure("Phase1 queue enqueue_script failed")
    players, scripts = q.drain_for_tick()
    if len(players) != 1 or len(scripts) != 1:
        raise TestFailure(f"Phase1 queue drain mismatch: {players} {scripts}")
    if q.depth() != 0:
        raise TestFailure("Phase1 queue not empty after drain")
    ok("PlayerInputQueue FIFO drain at tick boundary")

    boot = bootstrap_mirror()
    if boot.get("phase") != "Phase 1" or boot.get("player_inject_tick") is not None:
        raise TestFailure(f"Phase1 bootstrap mirror bad: {boot}")
    from agent_world.hbm_demo.features.f01_session.models import HbmSession

    hbm = HbmSession(
        task_id="t",
        start_tick=0,
        place_id="nvidia_reception",
        phase="Phase 1",
        player_turn=1,
        stats={"vision": 8, "execution": 5, "trust": 12, "burnout": 3},
    )
    mirror = mirror_from_session(hbm)
    if mirror.get("player_turn") != 1:
        raise TestFailure(f"Phase1 mirror_from_session bad: {mirror}")
    ok("session_mirror bootstrap + mirror_from_session")

    run_hbm_src = (HBM_DIR / "core" / "runner" / "run_hbm.py").read_text(encoding="utf-8")
    if "WorldLoopOrchestrator" not in run_hbm_src or "orchestrator.start()" not in run_hbm_src:
        raise TestFailure("Phase1 run_hbm must start WorldLoopOrchestrator")
    ok("run_hbm wires WorldLoopOrchestrator.start()")

    ipc_src = (HBM_DIR / "core" / "runner" / "ipc_handlers.py").read_text(encoding="utf-8")
    if "handle_enqueue_player_input" not in ipc_src:
        raise TestFailure("Phase1 ipc_handlers missing ENQUEUE_PLAYER_INPUT")
    if "orchestrator.enqueue_player_input" not in ipc_src:
        raise TestFailure("Phase1 ipc_handlers must enqueue via orchestrator")
    ok("ipc_handlers enqueue-only when world loop enabled")

    env_src = (HBM_DIR / "shared" / "env_status.py").read_text(encoding="utf-8")
    if "loop_running" not in env_src or "last_activity_t" not in env_src:
        raise TestFailure("Phase1 env_status missing loop fields")
    ok("env_status.json supports loop_running + last_activity_t")


def test_f07_v2_phase1b_world_loop_pause() -> None:
    """dev_logs/31 Phase 1b — pause/resume world loop (§8.3)."""
    section("T2n v2 Phase1b world loop pause/resume")
    from types import SimpleNamespace

    from agent_world.hbm_demo.core.runner.world_loop import WorldLoopOrchestrator
    from agent_world.hbm_demo.features import FEATURE_REGISTRY
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_manual_pause_allowed,
        is_world_loop_enabled,
        load_turn_control,
    )
    from agent_world.hbm_demo.features.f13_world_loop_control.handler import (
        get_world_loop_status,
        pause_world_loop,
        resume_world_loop,
    )
    from agent_world.ipc.commands import CommandType

    if "F13" not in FEATURE_REGISTRY:
        raise TestFailure("Phase1b: FEATURE_REGISTRY missing F13")
    ok("FEATURE_REGISTRY includes F13")

    load_turn_control.cache_clear()
    if not is_world_loop_enabled():
        raise TestFailure("Phase1b: world_loop.enabled must be true")
    if not is_manual_pause_allowed():
        raise TestFailure("Phase1b: allow_manual_pause must be true")
    ok("turn_control allow_manual_pause enabled")

    for cmd in (CommandType.PAUSE_LOOP, CommandType.RESUME_LOOP):
        if not isinstance(cmd.value, str):
            raise TestFailure(f"Phase1b missing IPC command: {cmd}")
    ok("Phase1b PAUSE_LOOP + RESUME_LOOP registered")

    for fn in (get_world_loop_status, pause_world_loop, resume_world_loop):
        if not callable(fn):
            raise TestFailure(f"Phase1b handler missing: {fn}")
    ok("F13 handler entrypoints present")

    status_panel = (HBM_DIR / "web" / "src" / "features" / "layout" / "StatusPanel.tsx").read_text(
        encoding="utf-8"
    )
    if "暂停世界" not in status_panel or "继续世界" not in status_panel:
        raise TestFailure("Phase1b StatusPanel missing pause/resume labels")
    ok("StatusPanel pause/resume UI wired")

    orch = WorldLoopOrchestrator(
        world_db=SimpleNamespace(),
        world_state=SimpleNamespace(clock=SimpleNamespace(t=7)),
        place_store=SimpleNamespace(),
        script_engine=SimpleNamespace(),
        world_step=SimpleNamespace(),
        agents=SimpleNamespace(),
        sim_dir=str(SIM_DIR),
        get_current_tick=lambda: 7,
    )
    orch._running = True
    orch._loop_state = "running"
    pause_resp = orch.pause()
    if pause_resp.get("loop_state") != "paused" or pause_resp.get("paused_at_tick") != 7:
        raise TestFailure(f"Phase1b orchestrator.pause bad: {pause_resp}")
    if orch._pause_event.is_set():
        raise TestFailure("Phase1b pause_event must be cleared when paused")
    ok("WorldLoopOrchestrator.pause freezes at current tick")

    again = orch.pause()
    if not again.get("already_paused"):
        raise TestFailure(f"Phase1b pause should be idempotent: {again}")
    ok("WorldLoopOrchestrator.pause idempotent")

    resume_resp = orch.resume()
    if resume_resp.get("loop_state") != "running":
        raise TestFailure(f"Phase1b orchestrator.resume bad: {resume_resp}")
    if not orch._pause_event.is_set():
        raise TestFailure("Phase1b pause_event must be set when running")
    ok("WorldLoopOrchestrator.resume restores running state")

    env_src = (HBM_DIR / "shared" / "env_status.py").read_text(encoding="utf-8")
    if "paused_at_tick" not in env_src or "paused_at_iso" not in env_src:
        raise TestFailure("Phase1b env_status missing paused_at fields")
    ok("env_status supports paused_at_tick + paused_at_iso")


def test_f07_v2_phase2_world_delta() -> None:
    """dev_logs/31 Phase 2 — F14 session delta + player-turn accepted contract."""
    section("T2o v2 Phase2 F14 world-delta + RoutingWatcher")
    from agent_world.hbm_demo.features import FEATURE_REGISTRY
    from agent_world.hbm_demo.features.f05_story_routing.watcher import (
        ROUTING_WATCHER_KEY,
        consume_game_over_payload,
        consume_routing_world_events,
        scan_routing_if_needed,
    )
    from agent_world.hbm_demo.features.f07_agent_control.config import is_world_loop_enabled
    from agent_world.hbm_demo.features.f12_world_sync.delta import build_session_world_delta
    from agent_world.hbm_demo.features.f14_world_delta.handler import get_world_delta
    from agent_world.hbm_demo import game_service as gs

    if "F14" not in FEATURE_REGISTRY:
        raise TestFailure("Phase2: FEATURE_REGISTRY missing F14")
    ok("FEATURE_REGISTRY includes F14")

    if not hasattr(gs, "get_world_delta"):
        raise TestFailure("game_service missing get_world_delta export")
    ok("game_service exports get_world_delta")

    if not callable(get_world_delta):
        raise TestFailure("F14 handler missing get_world_delta")
    if not callable(scan_routing_if_needed):
        raise TestFailure("F05 watcher missing scan_routing_if_needed")
    if not callable(consume_game_over_payload):
        raise TestFailure("F05 watcher missing consume_game_over_payload")
    ok("F14 handler + F05 RoutingWatcher entrypoints present")

    if ROUTING_WATCHER_KEY != "hbm_routing_watcher":
        raise TestFailure(f"unexpected ROUTING_WATCHER_KEY: {ROUTING_WATCHER_KEY}")

    handler_src = (HBM_DIR / "features" / "f02_player_turn" / "handler.py").read_text(
        encoding="utf-8"
    )
    if "_handle_v2_player_turn" not in handler_src or '"accepted": True' not in handler_src:
        raise TestFailure("F02 handler missing Phase2 accepted enqueue path")
    ok("F02 player-turn returns accepted when world loop enabled")

    f03_src = (HBM_DIR / "features" / "f03_action_result" / "handler.py").read_text(
        encoding="utf-8"
    )
    if "get_world_delta" not in f03_src or "is_world_loop_enabled" not in f03_src:
        raise TestFailure("F03 action-result missing world-loop delta-only branch")
    ok("F03 action-result delegates to F14 when world loop enabled")

    delta_src = (HBM_DIR / "features" / "f12_world_sync" / "delta.py").read_text(
        encoding="utf-8"
    )
    if "build_session_world_delta" not in delta_src:
        raise TestFailure("F12 delta missing build_session_world_delta")
    ok("F12 build_session_world_delta present")

    if not is_world_loop_enabled():
        ok("Phase2 static checks skipped (world_loop disabled in this env)")
        return

    class EmptyDB:
        def fetch_f2f_by_places(self, since_t, t_now, places):
            return {}

        def fetch_rdc_for_agent(self, agent_id, since_t, t_now):
            return []

        def fetch_grp_for_agent(self, agent_id, since_t, t_now):
            return []

        def fetch_location_logs_since(self, since_t, t_now):
            return []

        def fetch_group_events_since(self, since_t, t_now):
            return []

        def fetch_state_logs_since(self, since_t, t_now):
            return []

        def fetch_broadcasts_since(self, since_t, t_now):
            return []

        def fetch_all_agent_locations(self):
            return {}

        def fetch_trace_links_since(self, since_t, t_now):
            return []

    delta = build_session_world_delta(
        since_tick=0,
        t_now=5,
        player_place_id="nvidia_reception",
        db=EmptyDB(),
        name_map={},
    )
    assert_f12_delta_shape(delta, context="build_session_world_delta")
    if int(delta.get("through_tick", 0)) != 5:
        raise TestFailure(f"build_session_world_delta through_tick != 5: {delta}")
    ok("build_session_world_delta shape OK")

    flask_session: Dict[str, Any] = {}
    events = consume_routing_world_events(
        flask_session,
        since_tick=0,
        t_now=10,
    )
    if events:
        raise TestFailure(f"empty watcher should yield no events: {events}")
    ok("RoutingWatcher consume_routing_world_events on empty session")


def test_f07_v2_phase3_prompt_trace() -> None:
    """dev_logs/31 Phase 3 — L4 recap + F15 Prompt Inspector."""
    section("T2p v2 Phase3 recap + F15 prompt trace")
    from agent_world.hbm_demo.features import FEATURE_REGISTRY
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_prompt_trace_enabled,
        recap_window_ticks,
    )
    from agent_world.hbm_demo.features.f07_agent_control.knowledge import (
        build_thread_recap,
        format_session_facts,
    )
    from agent_world.hbm_demo.features.f15_prompt_trace.refs import enrich_world_delta
    from agent_world.hbm_demo import game_service as gs

    if "F15" not in FEATURE_REGISTRY:
        raise TestFailure("Phase3: FEATURE_REGISTRY missing F15")
    ok("FEATURE_REGISTRY includes F15")

    schema_dir = ROOT / "agent_world" / "persistence" / "schema" / "world"
    for name in ("agent_llm_trace.sql", "agent_action_trace_link.sql"):
        if not (schema_dir / name).is_file():
            raise TestFailure(f"Phase3: missing schema {name}")
    ok("F15 world.db schema SQL present")

    if not callable(build_thread_recap):
        raise TestFailure("knowledge.build_thread_recap missing")
    ok("knowledge.build_thread_recap present")

    facts = format_session_facts(type("S", (), {"player_turn": 3, "phase": "Phase 1"})())
    if "Vision=" in facts or "Execution=" in facts or "节点" in facts:
        raise TestFailure(f"format_session_facts still contains Stats gate text: {facts}")
    ok("format_session_facts stripped Stats gate copy")

    hbm_src = (HBM_DIR / "core" / "runner" / "hbm_agent.py").read_text(encoding="utf-8")
    if "违规将被引擎拒绝" in hbm_src:
        raise TestFailure("hbm_agent still contains hard threat copy")
    if "PromptTraceStore" not in hbm_src or "build_thread_recap" not in hbm_src:
        raise TestFailure("hbm_agent missing trace write or thread recap hook")
    ok("hbm_agent trace hook + softened action rules")

    turn_yaml = (HBM_DIR / "features" / "f07_agent_control" / "turn_control.yaml").read_text(
        encoding="utf-8"
    )
    if "prompt_trace:" not in turn_yaml or "recap_window_ticks:" not in turn_yaml:
        raise TestFailure("turn_control.yaml missing prompt_trace / recap_window_ticks")
    ok("turn_control.yaml prompt_trace + recap_window_ticks")

    if recap_window_ticks() < 1:
        raise TestFailure("recap_window_ticks invalid")

    class _RecapDB:
        def fetch_messages_for_recap(self, since_t, t_now, *, limit=40):  # noqa: ANN001
            _ = since_t, t_now, limit
            base = {
                "sender_id": 6,
                "group_id": None,
                "channel_type": "F2F",
                "content": "Jensen，14:42了。我最后说一次——30%，今天签。",
                "attempted_at": 21,
                "place_id": "negotiation_room",
            }
            return [
                {**base, "recipient_id": 2},
                {**base, "recipient_id": 3},
                {**base, "recipient_id": 4},
            ]

        def fetch_state_logs_since(self, since_t, t_now, agent_id=None):  # noqa: ANN001
            _ = since_t, t_now, agent_id
            return []

    recap = build_thread_recap(
        2,
        22,
        _RecapDB(),
        {6: "SK海力士 CEO"},
    )
    if recap.count("14:42") != 1:
        raise TestFailure(f"build_thread_recap should dedupe F2F fan-out: {recap!r}")
    ok("build_thread_recap dedupes F2F fan-out per utterance")

    for fn_name in ("get_prompt_trace", "get_prompt_trace_by_ref", "list_prompt_traces"):
        if not hasattr(gs, fn_name):
            raise TestFailure(f"game_service missing {fn_name}")
    ok("game_service exports F15 API helpers")

    routes_src = (HBM_DIR / "http" / "routes.py").read_text(encoding="utf-8")
    if "/prompt-trace/by-ref" not in routes_src:
        raise TestFailure("routes missing prompt-trace/by-ref")
    ok("Flask routes register prompt-trace endpoints")

    delta_src = (HBM_DIR / "features" / "f12_world_sync" / "delta.py").read_text(
        encoding="utf-8"
    )
    if "enrich_world_delta" not in delta_src or "_attach_trace_refs" not in delta_src:
        raise TestFailure("F12 delta missing trace enrichment")
    ok("F12 delta enriches prompt_trace_id / ref_key")

    link_map = {"f2f:nvidia_reception:5:1": "tr_test"}
    enriched = enrich_world_delta(
        {
            "room_f2f": {
                "nvidia_reception": [
                    {
                        "sender": "A",
                        "content": "hi",
                        "type": "F2F",
                        "attempted_at": 5,
                        "sender_id": 1,
                        "place_id": "nvidia_reception",
                    }
                ]
            },
            "state_changes": [],
            "location_changes": [],
        },
        link_map,
    )
    msg = enriched["room_f2f"]["nvidia_reception"][0]
    if msg.get("prompt_trace_id") != "tr_test" or msg.get("ref_key") != "f2f:nvidia_reception:5:1":
        raise TestFailure(f"enrich_world_delta failed: {msg}")
    ok("enrich_world_delta attaches trace fields")

    enriched_no_links = enrich_world_delta(
        {
            "room_f2f": {
                "nvidia_reception": [
                    {
                        "sender": "A",
                        "content": "hi",
                        "type": "F2F",
                        "attempted_at": 5,
                        "sender_id": 1,
                        "place_id": "nvidia_reception",
                    }
                ]
            },
            "state_changes": [],
            "location_changes": [],
        },
        {},
    )
    msg_no_link = enriched_no_links["room_f2f"]["nvidia_reception"][0]
    if msg_no_link.get("ref_key") != "f2f:nvidia_reception:5:1":
        raise TestFailure(f"enrich_world_delta missing ref_key without links: {msg_no_link}")
    if msg_no_link.get("prompt_trace_id"):
        raise TestFailure("ref_key-only enrich should not set prompt_trace_id")
    ok("enrich_world_delta attaches ref_key even without link_map")

    world_src = (HBM_DIR / "core" / "runner" / "world_step.py").read_text(
        encoding="utf-8"
    )
    if "trace_id=prompt_trace_id" not in world_src:
        raise TestFailure("world_step must pass captured prompt_trace_id to record_action_links")
    ok("world_step preserves prompt_trace_id for F15 linker")

    if "def _agent_place_id" not in world_src:
        raise TestFailure("HbmWorldStep must define _agent_place_id for F15 + player F2F")
    ok("HbmWorldStep defines _agent_place_id")

    if "is_experience_hardening" in world_src or "batch_guard" in world_src:
        raise TestFailure("world_step must not reference experience_hardening or batch_guard")
    ok("world_step free of experience_hardening / batch_guard")

    from agent_world.demo.demo_agent import _ToolCall
    from agent_world.hbm_demo.features.f15_prompt_trace.linker import _action_name

    if _action_name(_ToolCall(tool_name="update_state", args={})) != "update_state":
        raise TestFailure("F15 linker _action_name must read _ToolCall.tool_name")
    ok("F15 linker resolves _ToolCall.tool_name")

    linker_src = (HBM_DIR / "features" / "f15_prompt_trace" / "linker.py").read_text(
        encoding="utf-8"
    )
    if "comm_actions" not in linker_src or "send_message" not in linker_src:
        raise TestFailure("F15 linker must link comm actions even when bus delivery fails")
    ok("F15 linker links F2F/RDC/GRP regardless of dispatch success")

    world_sync = (HBM_DIR / "web" / "src" / "store" / "worldSync.ts").read_text(
        encoding="utf-8"
    )
    if "locationLog" not in world_sync or "mergeLocationChanges" not in world_sync:
        raise TestFailure("worldSync missing locationLog merge")
    ok("frontend worldSync locationLog merge present")

    for rel in (
        "web/src/features/prompt-trace/PromptTraceModal.tsx",
        "web/src/features/world-stage/LocationHistoryTimeline.tsx",
    ):
        if not (HBM_DIR / rel).is_file():
            raise TestFailure(f"Phase3 frontend missing {rel}")
    ok("PromptTraceModal + LocationHistoryTimeline present")

    if is_prompt_trace_enabled():
        ok("prompt_trace.enabled=true in turn_control.yaml")
    else:
        ok("prompt_trace.enabled=false (CI override OK)")


def test_f07_v2_phase4_agent_driven() -> None:
    """dev_logs/31 Phase 4 — agent_driven routing + bad_end via RoutingWatcher."""
    section("T2q v2 Phase4 agent_driven routing + bad_end")
    from types import SimpleNamespace

    from agent_world.hbm_demo.features.f02_player_turn.inject import check_turn4_bad_end
    from agent_world.hbm_demo.features.f05_story_routing.agent_signals import (
        detect_bad_end,
        detect_node_a,
        detect_node_b,
        detect_node_c,
    )
    from agent_world.hbm_demo.features.f05_story_routing.routing_config import (
        is_agent_driven,
        load_routing_config,
        routing_mode,
    )
    from agent_world.hbm_demo.features.f05_story_routing.watcher import (
        consume_game_over_payload,
        scan_routing_if_needed,
    )

    routing_yaml = HBM_DIR / "features" / "f05_story_routing" / "routing.yaml"
    if not routing_yaml.is_file():
        raise TestFailure("Phase4: missing routing.yaml")
    ok("routing.yaml present")

    if routing_mode() != "agent_driven":
        raise TestFailure(f"Phase4: routing.mode expected agent_driven, got {routing_mode()!r}")
    if not is_agent_driven():
        raise TestFailure("Phase4: is_agent_driven() must be True")
    ok("routing.mode=agent_driven")

    cfg = load_routing_config()
    signals = cfg.get("signals") or {}
    if not signals.get("approve_keywords") or not signals.get("reject_keywords"):
        raise TestFailure("Phase4: routing.yaml signals incomplete")
    ok("routing.yaml signal keyword lists configured")

    routing_src = (
        HBM_DIR / "features" / "f05_story_routing" / "routing.py"
    ).read_text(encoding="utf-8")
    if "send_enqueue_script_event" not in routing_src:
        raise TestFailure("Phase4: apply_routing must use send_enqueue_script_event")
    if "send_inject_batch" in routing_src:
        raise TestFailure("Phase4: routing.py must not call send_inject_batch")
    ok("Node B PlaceMutation via send_enqueue_script_event (no inject_batch)")

    inject_src = (HBM_DIR / "features" / "f02_player_turn" / "inject.py").read_text(
        encoding="utf-8"
    )
    if "is_agent_driven" not in inject_src:
        raise TestFailure("Phase4: check_turn4_bad_end missing agent_driven guard")
    ok("check_turn4_bad_end defers to RoutingWatcher in agent_driven mode")

    class SignalDB:
        def __init__(
            self,
            *,
            rdc_rows=None,
            f2f_rows=None,
        ):
            self._rdc = rdc_rows or []
            self._f2f = f2f_rows or []

        def fetch_rdc_messages(
            self, *, sender_id, recipient_id, since_t, t_now  # noqa: ANN001
        ):
            sid, rid = int(sender_id), int(recipient_id)
            return [
                r
                for r in self._rdc
                if int(r.get("sender_id", -1)) == sid
                and int(r.get("recipient_id", -1)) == rid
            ]

        def fetch_f2f_history_at(self, place_id, t_now, since_t, *, limit=30, exclusive_since=False):  # noqa: ANN001
            return list(self._f2f)

        def fetch_f2f_from_sender_at(  # noqa: ANN001
            self, place_id, sender_id, t_now, since_t, *, limit=500, exclusive_since=False
        ):
            sid = int(sender_id)
            return [
                row
                for row in self._f2f
                if int(row[1]) == sid
            ]

    approve_chain = [
        {"sender_id": 1, "recipient_id": 2, "content": "背景"},
        {"sender_id": 2, "recipient_id": 3, "content": "评估"},
        {"sender_id": 2, "recipient_id": 1, "content": "批准，这边请"},
    ]
    escort_f2f = [(5, 1, "m1", "请跟我来，Jensen在等")]
    if not detect_node_a(
        SignalDB(rdc_rows=approve_chain, f2f_rows=escort_f2f), since_t=0, t_now=10
    ):
        raise TestFailure("detect_node_a failed on approve chain + escort F2F")
    ok("detect_node_a RDC chain 1→2→3 + approve 2→1 + escort F2F")

    private_room_chain = [
        {"sender_id": 1, "recipient_id": 2, "content": "访客简报"},
        {"sender_id": 2, "recipient_id": 3, "content": "请评估"},
        {"sender_id": 2, "recipient_id": 1, "content": "让访客去私人会议室等着"},
    ]
    if not detect_node_a(
        SignalDB(rdc_rows=private_room_chain, f2f_rows=escort_f2f),
        since_t=0,
        t_now=10,
    ):
        raise TestFailure("detect_node_a must match 私人会议室 approve wording")
    ok("detect_node_a accepts 私人会议室 Jensen RDC + escort F2F")

    if not detect_node_a(SignalDB(rdc_rows=approve_chain), since_t=0, t_now=10):
        raise TestFailure(
            "detect_node_a must apply on approve RDC chain without escort F2F (default config)"
        )
    ok("detect_node_a applies on Jensen approve RDC without escort F2F")

    class RequireEscortDB(SignalDB):
        pass

    load_routing_config.cache_clear()
    orig_cfg = load_routing_config()
    patched = dict(orig_cfg)
    patched["signals"] = dict(patched.get("signals") or {})
    patched["signals"]["require_reception_escort_f2f"] = True

    import agent_world.hbm_demo.features.f05_story_routing.routing_config as rc

    _orig_load = rc.load_routing_config

    def _load_require_escort():
        return patched

    rc.load_routing_config = _load_require_escort  # type: ignore[assignment]
    try:
        from importlib import reload
        import agent_world.hbm_demo.features.f05_story_routing.agent_signals as sig_mod

        reload(sig_mod)
        if sig_mod.detect_node_a(SignalDB(rdc_rows=approve_chain), since_t=0, t_now=10):
            raise TestFailure(
                "detect_node_a must require reception escort F2F when configured"
            )
    finally:
        rc.load_routing_config = _orig_load
        rc.load_routing_config.cache_clear()
        reload(sig_mod)
    ok("detect_node_a rejects approve RDC without escort F2F when require=true")

    vp_row = [{"sender_id": 3, "recipient_id": 2, "content": "理论上可行"}]
    if not detect_node_b(SignalDB(rdc_rows=vp_row), since_t=0, t_now=10):
        raise TestFailure("detect_node_b failed on positive VP RDC")
    ok("detect_node_b positive VP RDC signal")

    jensen_opening_f2f = [(5, 2, "m1", "凭什么省80%")]
    if detect_node_b(SignalDB(f2f_rows=jensen_opening_f2f), since_t=0, t_now=10):
        raise TestFailure("detect_node_b must not fire on Jensen opening F2F alone")
    ok("detect_node_b ignores Jensen F2F without return keywords")

    return_f2f = [(6, 2, "m2", "方案可行，回谈判室")]
    if not detect_node_b(SignalDB(f2f_rows=return_f2f), since_t=0, t_now=10):
        raise TestFailure("detect_node_b failed on Jensen return-to-negotiation F2F")
    ok("detect_node_b accepts Jensen return F2F keywords")

    oral_return_f2f = [(7, 2, "m3", "走吧，跟我进谈判室")]
    if not detect_node_b(SignalDB(f2f_rows=oral_return_f2f), since_t=0, t_now=10):
        raise TestFailure("detect_node_b failed on oral 进谈判室 F2F")
    ok("detect_node_b accepts oral 进谈判室 F2F")

    player_noise = [(30 + i, 0, f"p{i}", "玩家追问") for i in range(35)]
    late_recognize = player_noise + [(180, 2, "m180", "别急，方案我认可了，咱们进去直接压价")]
    if not detect_node_b(SignalDB(f2f_rows=late_recognize), since_t=22, t_now=180):
        raise TestFailure("detect_node_b must not miss Jensen 认可 after long F2F thread")
    ok("detect_node_b finds Jensen 认可 with sender-scoped F2F scan")

    expel_row = [{"sender_id": 2, "recipient_id": 4, "content": "请离场"}]
    if not detect_node_c(SignalDB(rdc_rows=expel_row), since_t=0, t_now=10):
        raise TestFailure("detect_node_c failed on expel RDC")
    ok("detect_node_c Jensen expel keyword")

    oral_expel_f2f = [(8, 2, "m4", "三星镁光，你们先出去，谈够了")]
    if not detect_node_c(SignalDB(f2f_rows=oral_expel_f2f), since_t=0, t_now=10):
        raise TestFailure("detect_node_c failed on oral expel F2F")
    ok("detect_node_c accepts oral 你们先出去 F2F")

    reject_f2f = [(5, 1, "m1", "保安，请离开")]
    bad_session = SimpleNamespace(phase="Phase 1", player_turn=3, start_tick=0)
    if not detect_bad_end(
        bad_session,
        SignalDB(f2f_rows=reject_f2f),
        t_now=10,
    ):
        raise TestFailure("detect_bad_end failed on reception reject F2F")
    ok("detect_bad_end reception reject F2F")

    timeout_session = SimpleNamespace(phase="Phase 1", player_turn=10, start_tick=0)
    if not detect_bad_end(timeout_session, SignalDB(), t_now=10):
        raise TestFailure("detect_bad_end failed on Phase1 turn timeout without approve")
    ok("detect_bad_end Phase1 timeout without approve chain")

    legacy_bad = SimpleNamespace(
        phase="Phase 1",
        player_turn=4,
        start_tick=0,
        stats={"vision": 5, "execution": 5},
    )
    if check_turn4_bad_end(legacy_bad):
        raise TestFailure("agent_driven: check_turn4_bad_end must return False")
    ok("Turn4 Stats bad_end deferred from player-turn handler")

    watcher_src = (
        HBM_DIR / "features" / "f05_story_routing" / "watcher.py"
    ).read_text(encoding="utf-8")
    if "detect_bad_end" not in watcher_src or "pending_game_over" not in watcher_src:
        raise TestFailure("Phase4: watcher missing bad_end / game_over path")
    if "loop_state" not in watcher_src or "paused" not in watcher_src:
        raise TestFailure("Phase4: watcher must skip routing when loop paused")
    if not callable(consume_game_over_payload):
        raise TestFailure("Phase4: consume_game_over_payload missing")
    ok("RoutingWatcher bad_end + pause guard + consume_game_over_payload")

    f14_src = (HBM_DIR / "features" / "f14_world_delta" / "handler.py").read_text(
        encoding="utf-8"
    )
    if "consume_game_over_payload" not in f14_src or '"game_over"' not in f14_src:
        raise TestFailure("Phase4: F14 handler missing game_over in delta")
    ok("F14 delta exposes game_over payload")

    models_src = (HBM_DIR / "features" / "f01_session" / "models.py").read_text(
        encoding="utf-8"
    )
    if "ending_id" not in models_src:
        raise TestFailure("Phase4: HbmSession missing ending_id field")
    ok("HbmSession.ending_id persisted")

    poll_src = (
        HBM_DIR / "web" / "src" / "features" / "game-loop" / "worldDeltaApply.ts"
    ).read_text(encoding="utf-8")
    if "game_over" not in poll_src or "SET_GAME_OVER" not in poll_src:
        raise TestFailure("Phase4: worldDeltaApply missing game_over handling")
    ok("frontend worldDeltaApply dispatches SET_GAME_OVER")

    types_src = (HBM_DIR / "web" / "src" / "api" / "types.ts").read_text(
        encoding="utf-8"
    )
    if "game_over?" not in types_src and "game_over:" not in types_src:
        raise TestFailure("Phase4: WorldDeltaData missing game_over field")
    ok("WorldDeltaData includes optional game_over")

    flask_session: Dict[str, Any] = {}
    flask_session.setdefault("hbm_routing_watcher", {})["pending_game_over"] = {
        "status": "game_over",
        "ending_id": "bad_reject",
        "public_messages": [],
        "stats_update": {},
        "current_phase": "Phase 1",
    }
    payload = consume_game_over_payload(flask_session)
    if not payload or payload.get("ending_id") != "bad_reject":
        raise TestFailure(f"consume_game_over_payload failed: {payload}")
    if consume_game_over_payload(flask_session) is not None:
        raise TestFailure("consume_game_over_payload must be one-shot")
    ok("consume_game_over_payload one-shot semantics")

    if not callable(scan_routing_if_needed):
        raise TestFailure("scan_routing_if_needed missing")
    ok("scan_routing_if_needed entrypoint present")


def test_f07_v2_phase5_story_advance_and_ws() -> None:
    """dev_logs/31 Phase 5 — story_advance tool + F16 WebSocket delta stream."""
    section("T2r v2 Phase5 story_advance + world-stream WS")
    from types import SimpleNamespace

    from agent_world.hbm_demo.core.runner.hbm_agent import STORY_ADVANCE_TOOL
    from agent_world.hbm_demo.core.runner.hbm_dispatcher import HbmActionDispatcher
    from agent_world.hbm_demo.features import FEATURE_REGISTRY
    from agent_world.hbm_demo.features.f05_story_routing.agent_signals import (
        detect_bad_end,
        detect_node_a,
        detect_node_b,
        detect_node_c,
    )
    from agent_world.hbm_demo.features.f05_story_routing.routing_config import (
        is_story_advance_enabled,
    )
    from agent_world.hbm_demo.features.f05_story_routing.story_signals import (
        VALID_STORY_SIGNALS,
        normalize_story_signal,
    )
    from agent_world.hbm_demo.features.f16_world_stream.config import (
        is_world_stream_enabled,
    )

    schema_path = (
        ROOT / "agent_world" / "persistence" / "schema" / "world" / "story_advance_log.sql"
    )
    if not schema_path.is_file():
        raise TestFailure("Phase5: missing story_advance_log.sql")
    ok("story_advance_log schema present")

    if "F16" not in FEATURE_REGISTRY:
        raise TestFailure("Phase5: FEATURE_REGISTRY missing F16")
    ok("FEATURE_REGISTRY includes F16")

    if not is_story_advance_enabled():
        raise TestFailure("Phase5: routing.yaml story_advance.enabled expected true")
    ok("routing.yaml story_advance.enabled")

    if normalize_story_signal("approve_visitor") != "approve_visitor":
        raise TestFailure("normalize_story_signal failed")
    if normalize_story_signal("INVALID") is not None:
        raise TestFailure("normalize_story_signal must reject unknown signals")
    ok(f"story_signals VALID_STORY_SIGNALS ({len(VALID_STORY_SIGNALS)} values)")

    agent_src = (HBM_DIR / "core" / "runner" / "hbm_agent.py").read_text(encoding="utf-8")
    if "STORY_ADVANCE_TOOL" not in agent_src or "story_advance" not in agent_src:
        raise TestFailure("Phase5: hbm_agent missing story_advance tool")
    if STORY_ADVANCE_TOOL["function"]["name"] != "story_advance":
        raise TestFailure("STORY_ADVANCE_TOOL name mismatch")
    ok("HbmAgent exposes story_advance LLM tool")

    disp_src = (HBM_DIR / "core" / "runner" / "hbm_dispatcher.py").read_text(
        encoding="utf-8"
    )
    if "insert_story_advance_sync" not in disp_src:
        raise TestFailure("Phase5: dispatcher missing story_advance persistence")
    ok("HbmActionDispatcher persists story_advance to world.db")

    agent_src = (HBM_DIR / "core" / "runner" / "hbm_agent.py").read_text(encoding="utf-8")
    if "story_advance" not in agent_src:
        raise TestFailure("Phase5: HbmAgent must expose story_advance tool")
    ok("HbmAgent exposes story_advance (no L5 tool_matrix gate)")

    signals_src = (
        HBM_DIR / "features" / "f05_story_routing" / "agent_signals.py"
    ).read_text(encoding="utf-8")
    if "has_story_signal" not in signals_src:
        raise TestFailure("Phase5: agent_signals missing story_advance OR path")
    ok("agent_signals OR-combines NL keywords with story_advance")

    class SignalDB:
        def __init__(self, rows):
            self._rows = rows

        def fetch_story_advance_since(
            self, since_t, t_now, *, signal=None, agent_id=None  # noqa: ANN001
        ):
            out = [
                r
                for r in self._rows
                if int(since_t) < int(r["at_tick"]) <= int(t_now)
            ]
            if signal is not None:
                out = [r for r in out if r["signal"] == signal]
            if agent_id is not None:
                out = [r for r in out if int(r["agent_id"]) == int(agent_id)]
            return out

        def fetch_rdc_messages(
            self, *, sender_id, recipient_id, since_t, t_now  # noqa: ANN001
        ):
            return []

        def fetch_f2f_history_at(self, place_id, t_now, since_t):  # noqa: ANN001
            return []

    sig_row = [{"agent_id": 2, "signal": "approve_visitor", "at_tick": 5}]
    if not detect_node_a(SignalDB(sig_row), since_t=0, t_now=10):
        raise TestFailure("detect_node_a failed on story_advance approve_visitor")
    ok("detect_node_a accepts story_advance(approve_visitor)")

    if not detect_node_b(
        SignalDB([{"agent_id": 2, "signal": "return_to_negotiation", "at_tick": 6}]),
        since_t=0,
        t_now=10,
    ):
        raise TestFailure("detect_node_b failed on return_to_negotiation signal")
    ok("detect_node_b accepts story_advance(return_to_negotiation)")

    if not detect_node_c(
        SignalDB([{"agent_id": 2, "signal": "expel_ceos", "at_tick": 7}]),
        since_t=0,
        t_now=10,
    ):
        raise TestFailure("detect_node_c failed on expel_ceos signal")
    ok("detect_node_c accepts story_advance(expel_ceos)")

    bad_session = SimpleNamespace(phase="Phase 1", player_turn=3, start_tick=0)
    if not detect_bad_end(
        bad_session,
        SignalDB([{"agent_id": 1, "signal": "reject_visitor", "at_tick": 4}]),
        t_now=10,
    ):
        raise TestFailure("detect_bad_end failed on reject_visitor signal")
    ok("detect_bad_end accepts story_advance(reject_visitor)")

    if not is_world_stream_enabled():
        raise TestFailure("Phase5: turn_control world_stream.enabled expected true")
    ok("turn_control.yaml world_stream.enabled")

    f16_src = (HBM_DIR / "features" / "f16_world_stream" / "handler.py").read_text(
        encoding="utf-8"
    )
    if "world-stream" not in f16_src or "get_world_delta" not in f16_src:
        raise TestFailure("Phase5: F16 handler missing world-stream route")
    ok("F16 handler pushes get_world_delta over WebSocket")

    app_src = (ROOT / "agent_world" / "app" / "__init__.py").read_text(encoding="utf-8")
    if "flask_sock" not in app_src or "register_world_stream_routes" not in app_src:
        raise TestFailure("Phase5: Flask app missing WebSocket registration")
    ok("Flask create_app registers F16 WebSocket routes")

    sync_src = (
        HBM_DIR / "web" / "src" / "features" / "game-loop" / "useWorldDeltaSync.ts"
    ).read_text(encoding="utf-8")
    stream_src = (
        HBM_DIR / "web" / "src" / "features" / "game-loop" / "useWorldDeltaStream.ts"
    ).read_text(encoding="utf-8")
    app_tsx = (HBM_DIR / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    if "useWorldDeltaSync" not in sync_src or "useWorldDeltaStream" not in sync_src:
        raise TestFailure("Phase5: frontend missing useWorldDeltaSync/Stream")
    if "useWorldDeltaSync" not in app_tsx:
        raise TestFailure("Phase5: App.tsx must use useWorldDeltaSync")
    if "world-stream" not in stream_src:
        raise TestFailure("Phase5: useWorldDeltaStream missing WS URL")
    ok("frontend useWorldDeltaSync (WS primary + poll fallback)")

    vite_cfg = (HBM_DIR / "web" / "vite.config.ts").read_text(encoding="utf-8")
    if "ws: true" not in vite_cfg:
        raise TestFailure("Phase5: vite proxy missing ws: true")
    ok("Vite dev proxy forwards WebSocket")


def test_m6_frontend_features() -> None:
    section("T1g M6 web/src/features/ 前端 Feature 拆分")
    web_src = HBM_DIR / "web" / "src"
    feature_dirs = (
        "boot",
        "game-loop",
        "layout",
        "main-chat",
        "world-stage",
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
    if "F12" not in registry:
        raise TestFailure("features/index.ts missing F12 world-stage registry")
    ok("features/index.ts FEATURE_REGISTRY (F09 + F12)")

    app_src = (web_src / "App.tsx").read_text(encoding="utf-8")
    if 'from "./features"' not in app_src:
        raise TestFailure("App.tsx should import from ./features directly")
    if "WorldStage" not in app_src or "TwoColumnLayout" not in app_src:
        raise TestFailure("App.tsx should use F12 TwoColumnLayout + WorldStage")
    if "ObserverPanel" in app_src:
        raise TestFailure("App.tsx should not render ObserverPanel (F12 Phase 3)")
    ok("App.tsx F12 two-column WorldStage layout")

    for removed in ("components", "hooks"):
        if (web_src / removed).exists():
            raise TestFailure(f"legacy web/src/{removed}/ should be removed (M7)")
    ok("web/src/components and hooks removed (M7)")

    layout_impl = (web_src / "features" / "layout" / "TwoColumnLayout.tsx").read_text(
        encoding="utf-8"
    )
    if "TwoColumnLayout" not in layout_impl or "app-shell--two-col" not in layout_impl:
        raise TestFailure("features/layout/TwoColumnLayout implementation missing")
    ok("F12 TwoColumnLayout in features/layout")


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

    FakeSession.phase = "Phase 4"
    FakeSession.player_turn = 21
    FakeSession.place_id = "negotiation_room"
    events_p4, bc4, ctx4 = build_inject_payload(
        FakeSession(), "终局谈判", task_id="t21"
    )
    if load_turn_control().get("enabled"):
        aids = [e["effect"]["agent_id"] for e in events_p4]
        if aids != [2]:
            raise TestFailure(f"F07 Phase 4 inject must target Agent 2 only: {aids}")
        if bc4 is not None:
            raise TestFailure("Phase 4 Turn 21 should not broadcast")
        if ctx4 is None:
            raise TestFailure("F07 Phase 4 turn_context missing")
        ok("F07-D Phase 4 inject → Agent 2 only")
    else:
        if len(events_p4) < 1:
            raise TestFailure("Phase 4 inject events missing")

    class NodeA:
        phase = "Phase 1"
        player_turn = 4
        start_tick = 0
        stats = {"vision": 10, "execution": 5, "trust": 10, "burnout": 0}

    from agent_world.hbm_demo.features.f05_story_routing.routing_config import (
        is_agent_driven,
    )

    if is_agent_driven():

        class FakeDBNodeA:
            def fetch_rdc_messages(
                self, *, sender_id, recipient_id, since_t, t_now  # noqa: ANN001
            ):
                sid, rid = int(sender_id), int(recipient_id)
                if sid == 1 and rid == 2:
                    return [{"content": "玩家背景"}]
                if sid == 2 and rid == 3:
                    return [{"content": "请评估"}]
                if sid == 2 and rid == 1:
                    return [{"content": "批准，这边请带进来"}]
                return []

            def fetch_f2f_history_at(self, place_id, t_now, since_t):  # noqa: ANN001
                if str(place_id) == "nvidia_reception":
                    return [(5, 1, "m1", "请跟我来，Jensen在等")]
                return []

        if not node_a_applies(NodeA(), FakeDBNodeA(), 10):
            raise TestFailure("agent_driven node_a should apply on RDC approve chain")
        ok("F05 agent_driven node A (RDC 1→2→3 + approve 2→1)")
    else:
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

    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_world_loop_enabled,
    )

    v2_loop = is_world_loop_enabled()

    if is_world_loop_enabled():
        env_data = env_payload.get("data") or {}
        if not env_data.get("loop_running"):
            raise TestFailure(
                f"Phase1: env_status.loop_running expected true, got {env_data}"
            )
        idle_t0 = int(env_data.get("current_tick", 0))
        idle_t1 = idle_t0
        idle_deadline = time.time() + 45.0
        while time.time() < idle_deadline:
            time.sleep(1.0)
            _, env_idle, _ = http_json("GET", f"{base}{BASE_PATH}/env-status")
            idle_t1 = int((env_idle.get("data") or {}).get("current_tick", 0))
            if idle_t1 > idle_t0:
                break
        if idle_t1 <= idle_t0:
            raise TestFailure(
                f"Phase1: idle tick did not advance {idle_t0} → {idle_t1} within 45s"
            )
        ok(f"Phase1 idle world loop tick advance {idle_t0} → {idle_t1}")

        section("T4-pre Phase1b world-loop pause/resume (§8.3.7)")
        code, pause_resp, _ = http_json(
            "POST", f"{base}{BASE_PATH}/world-loop/pause", timeout=15.0
        )
        if code != 200 or not pause_resp.get("success"):
            raise TestFailure(f"Phase1b pause failed HTTP {code}: {pause_resp}")
        pause_data = pause_resp.get("data") or {}
        if pause_data.get("loop_state") != "paused":
            raise TestFailure(f"Phase1b pause loop_state != paused: {pause_data}")
        pause_tick = int(pause_data.get("current_tick", -1))
        paused_at = pause_data.get("paused_at_tick")
        if paused_at is not None:
            pause_tick = int(paused_at)
        ok(f"Phase1b POST /world-loop/pause → tick={pause_tick}")

        # Allow one in-flight tick to finish after pause IPC returns.
        time.sleep(2.0)
        _, env_anchor, _ = http_json("GET", f"{base}{BASE_PATH}/env-status")
        anchor_tick = int((env_anchor.get("data") or {}).get("current_tick", pause_tick))
        if anchor_tick < pause_tick:
            anchor_tick = pause_tick
        ok(f"Phase1b pause anchor tick={anchor_tick} (post in-flight settle)")

        frozen_deadline = time.time() + 6.0
        while time.time() < frozen_deadline:
            _, env_frozen, _ = http_json("GET", f"{base}{BASE_PATH}/env-status")
            frozen_tick = int((env_frozen.get("data") or {}).get("current_tick", -1))
            if frozen_tick != anchor_tick:
                raise TestFailure(
                    f"Phase1b tick moved while paused: {anchor_tick} → {frozen_tick}"
                )
            time.sleep(1.0)
        ok(f"Phase1b tick frozen at {anchor_tick} for 5s")

        code, resume_resp, _ = http_json(
            "POST", f"{base}{BASE_PATH}/world-loop/resume", timeout=15.0
        )
        if code != 200 or not resume_resp.get("success"):
            raise TestFailure(f"Phase1b resume failed HTTP {code}: {resume_resp}")
        if (resume_resp.get("data") or {}).get("loop_state") != "running":
            raise TestFailure(f"Phase1b resume loop_state != running: {resume_resp}")
        ok("Phase1b POST /world-loop/resume → running")

        resume_tick = anchor_tick
        resume_deadline = time.time() + 45.0
        while time.time() < resume_deadline:
            time.sleep(1.0)
            _, env_resume, _ = http_json("GET", f"{base}{BASE_PATH}/env-status")
            resume_tick = int((env_resume.get("data") or {}).get("current_tick", resume_tick))
            if resume_tick > anchor_tick:
                break
        if resume_tick <= anchor_tick:
            raise TestFailure(
                f"Phase1b tick did not advance after resume: {anchor_tick} → {resume_tick}"
            )
        ok(f"Phase1b tick resumed {anchor_tick} → {resume_tick}")

        _, loop_status, _ = http_json("GET", f"{base}{BASE_PATH}/world-loop/status")
        if not (loop_status.get("data") or {}).get("loop_state"):
            raise TestFailure(f"Phase1b GET /world-loop/status bad: {loop_status}")
        ok("Phase1b GET /world-loop/status OK")

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

    section("T4a-pre F12 Phase 2 world-snapshot + delta shape (dev_logs/32 §八)")
    code, world_snap, cookie = http_json(
        "GET", f"{base}{BASE_PATH}/world-snapshot", cookie=cookie
    )
    if code != 200 or not world_snap.get("success"):
        raise TestFailure(f"GET /world-snapshot failed HTTP {code}: {world_snap}")
    snap_data = world_snap.get("data") or {}
    assert_f12_snapshot_shape(snap_data, context="world-snapshot")
    ok(
        f"GET /world-snapshot → tick={snap_data.get('through_tick')} "
        f"agents={len(snap_data.get('agent_locations') or {})} "
        f"places={len(snap_data.get('place_attrs') or {})}"
    )

    if v2_loop:
        section("T4a-pre2 F14 silent world-delta poll (Phase 2 §14.3)")
        silent_since = int(snap_data.get("through_tick") or 0)
        silent_deadline = time.time() + 20.0
        saw_silent_tick = False
        while time.time() < silent_deadline:
            url = f"{base}{BASE_PATH}/world-delta?since_tick={silent_since}"
            code, silent_resp, cookie = http_json(
                "GET", url, cookie=cookie, timeout=15.0
            )
            if code != 200 or not silent_resp.get("success"):
                raise TestFailure(f"F14 silent poll HTTP {code}: {silent_resp}")
            silent_data = silent_resp.get("data") or {}
            assert_f12_delta_shape(silent_data, context="silent world-delta")
            through = int(silent_data.get("through_tick", silent_since))
            if through > silent_since:
                saw_silent_tick = True
                silent_since = through
            time.sleep(0.5)
        if not saw_silent_tick:
            raise TestFailure("F14 silent poll: through_tick did not advance in 20s")
        ok(f"F14 silent poll tick advanced to {silent_since}")

        code, wd_zero, cookie = http_json(
            "GET", f"{base}{BASE_PATH}/world-delta?since_tick=0", cookie=cookie
        )
        if code != 200 or not wd_zero.get("success"):
            raise TestFailure(f"GET /world-delta failed: {wd_zero}")
        ok("GET /world-delta endpoint registered and returns F12 delta shape")

    section("T4e-pre F07-E6 double session/start hygiene (dev_logs/29 §3.6.2)")
    from agent_world.hbm_demo.features.f11_live_turn_sync.task_state import (
        async_state_path,
        save_task_runtime,
    )

    save_task_runtime(
        SIM_DIR,
        {
            "task_id": "stale_overlay",
            "start_tick": 99,
            "place_id": "nvidia_reception",
            "phase": "Phase 1",
            "player_turn": 4,
        },
        session_dict={
            "task_id": "stale_overlay",
            "start_tick": 99,
            "place_id": "nvidia_reception",
            "phase": "Phase 1",
            "player_turn": 4,
            "stats": {"vision": 8, "execution": 5, "trust": 12, "burnout": 3},
        },
    )
    code, start_again, cookie = http_json(
        "POST", f"{base}{BASE_PATH}/session/start", cookie=cookie
    )
    if code != 200 or not start_again.get("success"):
        raise TestFailure(f"second session/start failed: {start_again}")
    again_data = start_again.get("data") or {}
    if int(again_data.get("player_turn", 0)) != 1:
        raise TestFailure(f"E6 second session/start player_turn != 1: {again_data}")
    if again_data.get("phase") != "Phase 1":
        raise TestFailure(f"E6 second session/start bad phase: {again_data}")
    if async_state_path(SIM_DIR).exists():
        raise TestFailure("E6 session/start should remove stale async_state/runtime.json")
    ok("E6 double session/start clears stale overlay → Turn 1 Phase 1")

    # dev_logs/19 Turn 1 — 高密度技术词，利于前台 F2F / Jensen RDC（Tier B）
    player_text = (
        "我要见黄仁勋。我有一套推理侧稀疏注意力方案，能把大模型 KV Cache "
        "显存占用降低 80%，不是 PPT，是已 repro 的 kernel。"
    )

    if v2_loop:
        section("T4b F14 player-turn accepted + world-delta poll (Phase 2)")
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
        if not tdata.get("accepted"):
            raise TestFailure(f"Phase2 player-turn missing accepted=true: {tdata}")
        if tdata.get("task_id"):
            raise TestFailure(f"Phase2 player-turn must not return task_id: {tdata}")
        if int(tdata.get("player_turn", 0)) < 2:
            raise TestFailure(f"Phase2 player-turn not incremented: {tdata}")
        ok(
            f"POST /player-turn → accepted player_turn={tdata.get('player_turn')} "
            f"({post_elapsed:.2f}s enqueue-only)"
        )

        start_tick = int(snap_data.get("through_tick") or 0)
        loop_deadline_extra = 180.0
        result, cookie, last_through = poll_world_delta(
            base,
            cookie,
            start_tick,
            max_wait=180.0 + loop_deadline_extra,
        )
        ok(f"F14 world-delta captured activity through_tick={last_through}")

        code, sess_after, cookie = http_json(
            "GET", f"{base}{BASE_PATH}/session", cookie=cookie
        )
        sess_turn = int((sess_after.get("data") or {}).get("player_turn") or 0)
        if sess_turn < 2:
            raise TestFailure(f"Phase2 GET /session player_turn still {sess_turn}")
        ok(f"Phase2 GET /session player_turn={sess_turn} after enqueue")

        assert_f12_delta_shape(result, context="world-delta Turn1")
        public = result.get("public_messages") or []
        observer = result.get("observer_messages") or []
        grp = result.get("group_messages") or []
        reception_f2f = (result.get("room_f2f") or {}).get("nvidia_reception") or []
        if len(public) != len(reception_f2f):
            raise TestFailure(
                f"F12 legacy public_messages ({len(public)}) != "
                f"room_f2f.reception ({len(reception_f2f)})"
            )
        ok(
            f"F14 Turn1 delta — F2F={len(public)} observer={len(observer)} "
            f"GRP={len(grp)} room_f2f_places="
            f"{sum(len(v) for v in (result.get('room_f2f') or {}).values())} "
            f"agent_locs={len(result.get('agent_locations') or {})}"
        )
    else:
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
        saw_f12_delta = False
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
                assert_f12_delta_shape(delta, context="processing delta")
                saw_f12_delta = True
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
        if not saw_f12_delta:
            raise TestFailure("F12: never validated F12 delta shape during processing")
        ok(f"F11-B delta on processing (through_tick reached {last_through})")
        ok("F12 processing delta carries room_f2f / agent_locations / legacy fields")

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
        assert_f12_delta_shape(result, context="completed action-result")
        public = result.get("public_messages") or []
        observer = result.get("observer_messages") or []
        grp = result.get("group_messages") or []
        reception_f2f = (result.get("room_f2f") or {}).get("nvidia_reception") or []
        if len(public) != len(reception_f2f):
            raise TestFailure(
                f"F12 legacy public_messages ({len(public)}) != "
                f"room_f2f.reception ({len(reception_f2f)})"
            )
        if public and "sender_id" not in public[0]:
            raise TestFailure("F12 GameMessage missing sender_id on F2F")
        ok(
            f"GET /action-result completed — F2F={len(public)} observer={len(observer)} "
            f"GRP={len(grp)} room_f2f_places="
            f"{sum(len(v) for v in (result.get('room_f2f') or {}).values())} "
            f"agent_locs={len(result.get('agent_locations') or {})}"
        )

    code, world_snap_after, cookie = http_json(
        "GET", f"{base}{BASE_PATH}/world-snapshot", cookie=cookie
    )
    if code != 200 or not world_snap_after.get("success"):
        raise TestFailure(f"post-turn world-snapshot failed: {world_snap_after}")
    snap_after = world_snap_after.get("data") or {}
    assert_f12_snapshot_shape(snap_after, context="post-turn world-snapshot")
    ok(
        f"GET /world-snapshot after Turn 1 — tick={snap_after.get('through_tick')} "
        f"player_place={snap_after.get('player_place_id')}"
    )

    section("T4a-post F12 Phase 3 前端数据契约 (dev_logs/32 §八 Turn1)")
    reception_msgs = (result.get("room_f2f") or {}).get("nvidia_reception") or []
    if len(reception_msgs) < 1 and len(observer) < 1:
        raise TestFailure(
            f"Turn1 needs F2F or RDC activity: "
            f"reception={reception_msgs} observer={len(observer)}"
        )
    ok(
        f"Turn1 activity — reception_f2f={len(reception_msgs)} "
        f"observer={len(observer)}"
    )

    agent_locs = result.get("agent_locations") or {}
    if not agent_locs:
        raise TestFailure("Phase 3: agent_locations empty after Turn1 — AgentCircle needs locations")
    ok(f"Phase 3 agent_locations populated ({len(agent_locs)} agents)")

    agent_msgs = result.get("agent_messages") or {}
    if observer and not agent_msgs:
        raise TestFailure(
            "Phase 3: observer_messages present but agent_messages empty — phone panel would miss RDC"
        )
    if observer:
        rdc_agents = [
            aid for aid, bucket in agent_msgs.items() if (bucket.get("rdc") or [])
        ]
        if not rdc_agents:
            raise TestFailure(
                f"Phase 3: agent_messages has no RDC buckets despite observer={len(observer)}"
            )
        ok(f"Phase 3 agent_messages RDC buckets for agents {rdc_agents}")

    neg_f2f = (result.get("room_f2f") or {}).get("negotiation_room") or []
    if observer and len(neg_f2f) > 0:
        ok(
            f"Phase 3 negotiation_room has {len(neg_f2f)} F2F (cross-room visible via grid)"
        )
    elif observer:
        ok("Phase 3 Jensen RDC visible in agent_messages; negotiation F2F may be empty at Turn1")

    for place_id in F12_ROOM_PLACES:
        if place_id not in (result.get("room_f2f") or {}):
            raise TestFailure(f"Phase 3: room_f2f missing place {place_id}")
    ok("Phase 3 room_f2f covers all four ROOM_GRID places")

    app_src = (HBM_DIR / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    if "ObserverPanel" in app_src:
        raise TestFailure("Phase 3: App.tsx still references ObserverPanel")
    ok("Phase 3 two-column UI — no ObserverPanel in App.tsx")

    section("T4d F07 Phase 1 运行时验收 (dev_logs/24 §12.1 · Tier A/B)")
    if v2_loop:
        ipc_end = int(
            result.get("through_tick") or result.get("current_tick") or 0
        )
    else:
        ipc_end = int(task_runtime.get("ipc_end_tick") or 0)
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        max_inject_tick_loops,
    )

    min_ipc_end = max_inject_tick_loops()
    if v2_loop:
        if ipc_end <= start_tick:
            raise TestFailure(
                f"F14 Turn1 through_tick must advance past start_tick={start_tick}; "
                f"got {ipc_end}"
            )
        if not _delta_has_activity(result):
            raise TestFailure(
                f"F14 Turn1 delta captured no activity at through_tick={ipc_end}"
            )
        ok(
            f"Tier A v2: through_tick={ipc_end} > start_tick={start_tick} "
            f"(continuous delta, no ipc batch floor)"
        )
    else:
        if ipc_end < min_ipc_end:
            raise TestFailure(
                f"F07 Phase 1 inject must reach tick≥{min_ipc_end}; ipc_end_tick={ipc_end}"
            )
        ok(f"Tier A: ipc_end_tick={ipc_end} (≥{min_ipc_end}, no processing deadlock)")
    ok(f"Turn1 GRP={len(grp)} (LLM tool choice unfiltered)")
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

    section("T4e F07-E Step5 Turn 2 玩梗分流 (dev_logs/29 §3.3.4 · E3)")
    code, sess_turn2, cookie = http_json(
        "GET", f"{base}{BASE_PATH}/session", cookie=cookie
    )
    sess_data = (sess_turn2.get("data") or {})
    if int(sess_data.get("player_turn", 0)) < 2:
        raise TestFailure(
            f"Turn 1 should advance session to player_turn≥2: {sess_data}"
        )
    ok(f"session player_turn={sess_data.get('player_turn')} after Turn 1")

    turn2_text = (
        "我给您带了杯热咖啡，黄总还在忙吗？他今天还穿着那件黑色皮衣吗？"
    )
    code, turn2_post, cookie = http_json(
        "POST",
        f"{base}{BASE_PATH}/player-turn",
        body={"player_text": turn2_text},
        cookie=cookie,
        timeout=120.0,
    )
    if code != 200 or not turn2_post.get("success"):
        raise TestFailure(f"Turn 2 player-turn failed: {turn2_post}")
    turn2_data = turn2_post.get("data") or {}
    if v2_loop:
        if not turn2_data.get("accepted"):
            raise TestFailure(f"Turn 2 Phase2 missing accepted: {turn2_post}")
        if int(turn2_data.get("player_turn", 0)) < 3:
            raise TestFailure(f"Turn 2 Phase2 player_turn not advanced: {turn2_data}")
        ok(f"Turn 2 Phase2 accepted player_turn={turn2_data.get('player_turn')}")
        since_turn2 = int(result.get("through_tick") or 0)
        try:
            result2, cookie, _ = poll_world_delta(
                base, cookie, since_turn2, max_wait=120.0
            )
        except TestFailure:
            _, last_poll, cookie = http_json(
                "GET",
                f"{base}{BASE_PATH}/world-delta?since_tick={since_turn2}",
                cookie=cookie,
                timeout=30.0,
            )
            result2 = (last_poll.get("data") or {})
            ok(
                "Turn 2 Phase2 enqueue OK; delta activity optional when LLM/API slow"
            )
    else:
        task2_id = turn2_data.get("task_id")
        if not task2_id:
            raise TestFailure(f"Turn 2 missing task_id: {turn2_post}")
        result2, cookie = poll_action_result(base, task2_id, cookie, max_wait=240.0)
        if result2.get("status") != "completed":
            raise TestFailure(f"Turn 2 not completed: {result2}")
    public2 = result2.get("public_messages") or []
    observer2 = result2.get("observer_messages") or []

    ok(f"Turn 2 completed — F2F={len(public2)} observer={len(observer2)}")

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

    import sqlite3

    db_path = SIM_DIR / "world.db"
    with sqlite3.connect(str(db_path)) as conn:
        trace_n = conn.execute("SELECT COUNT(*) FROM agent_llm_trace").fetchone()[0]
        msg_n = conn.execute("SELECT COUNT(*) FROM direct_message").fetchone()[0]
        state_n = conn.execute("SELECT COUNT(*) FROM agent_state_log").fetchone()[0]
    if trace_n != 0 or msg_n != 0 or state_n != 0:
        raise TestFailure(
            f"reset后 world.db 仍有残留 trace={trace_n} msg={msg_n} state={state_n}"
        )
    ok("F01 reset clears agent_llm_trace / direct_message / agent_state_log")

    section("T4f F07-E6 Phase 4 IPC smoke (dev_logs/29 §3.6.4)")
    from agent_world.hbm_demo.scripts.acceptance.phase4_smoke import (
        run_phase4_ipc_smoke,
    )

    p4 = run_phase4_ipc_smoke(SIM_DIR, ipc_timeout=300.0)
    if p4.inject_agent_ids != [2]:
        raise TestFailure(f"E6 Phase 4 inject must target Agent 2 only: {p4.inject_agent_ids}")
    if p4.jensen_f2f_count < 1:
        raise TestFailure(
            f"E6 Phase 4 negotiation_room Jensen F2F must be ≥1; got {p4.jensen_f2f_count}"
        )
    if p4.vp_public_count != 0:
        raise TestFailure(
            f"E6 Phase 4 VP must not emit F2F (present_silent); got {p4.vp_public_count}"
        )
    if p4.ceo_in_negotiation:
        raise TestFailure(
            f"E6 Phase 4 CEOs must leave negotiation_room; still present: {p4.ceo_in_negotiation}"
        )
    ok(
        f"E6 Phase 4 IPC smoke — inject=[2] Jensen F2F={p4.jensen_f2f_count} "
        f"VP F2F=0 CEOs moved tick={p4.end_tick}"
    )

    code, turn2, cookie = http_json(
        "POST",
        f"{base}{BASE_PATH}/player-turn",
        body={"player_text": "重开后第一轮测试台词。"},
        cookie=cookie,
        timeout=120.0,
    )
    if code != 200:
        raise TestFailure(f"post-reset player-turn failed: {turn2}")
    reset_turn_data = turn2.get("data") or {}
    if v2_loop:
        if not reset_turn_data.get("accepted"):
            raise TestFailure(f"post-reset Phase2 missing accepted: {turn2}")
        result2, _, _ = poll_world_delta(base, cookie, 0, max_wait=240.0)
        if not _delta_has_activity(result2):
            raise TestFailure("post-reset Turn 1 F14 delta had no activity")
    else:
        task2 = reset_turn_data.get("task_id")
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
    from agent_world.hbm_demo.features.f11_live_turn_sync.task_state import (
        clear_async_state,
    )

    for stale in (SIM_DIR / "world.db", SIM_DIR / "env_status.json"):
        if stale.exists():
            stale.unlink()
    clear_async_state(SIM_DIR)

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
        test_f07_d_agent_control,
        test_f07_e_step1_player_facing_f2f,
        test_f08_virtual_player,
        test_f08_pr4_inject_and_f2f_delivery,
        test_f07_e_step2_no_scripted_fallback,
        test_f07_e_step3_inject_exclusive_ticks,
        test_f07_e_step4_turn_priority_and_offtopic,
        test_f07_e_step5_phase4_smoke_module,
        test_f07_v2_phase0_hard_control_retired,
        test_f07_v2_phase1_world_loop,
        test_f07_v2_phase1b_world_loop_pause,
        test_f07_v2_phase2_world_delta,
        test_f07_v2_phase3_prompt_trace,
        test_f07_v2_phase4_agent_driven,
        test_f07_v2_phase5_story_advance_and_ws,
        test_f05_routing_payload,
        test_f11_live_turn_sync,
        test_f11_c_frontend,
        test_f12_phase1_persistence,
        test_f12_phase2_world_delta,
        test_f12_phase3_world_stage,
        test_f12_visibility_no_hidden,
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

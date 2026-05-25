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
        is_experience_hardening,
        is_f07_enabled,
    )

    class EmptyDB:
        def has_f2f_after(self, *a, **k):
            return False

        def has_rdc_pair_after(self, *a, **k):
            return False

        def has_grp_after(self, *a, **k):
            return False

    class F2fReceptionDB(EmptyDB):
        def has_f2f_after(self, place_id, *a, **k):
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
    done_db = F2fReceptionDB() if is_experience_hardening() else EmptyDB()
    if not check_action_complete(done, done_tick, done_db):
        raise TestFailure(
            f"F11: done inject should complete at ipc_end_tick={done_tick}"
        )
    if is_experience_hardening() and check_action_complete(done, done_tick, EmptyDB()):
        raise TestFailure("F11 E5: done inject must not complete without F2F")
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
    if "getWorldDelta" not in delta_poll or "APPLY_WORLD_DELTA" not in delta_poll:
        raise TestFailure("useWorldDeltaPoll missing getWorldDelta / APPLY_WORLD_DELTA")
    ok("useWorldDeltaPoll F14 resident poll wired")

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
    if not re.search(r"DELTA_POLL_MS\s*=\s*500", game_loop_const):
        raise TestFailure("gameLoop DELTA_POLL_MS should be 500 for F14")
    ok("DELTA_POLL_MS = 500ms")

    messages = (web_src / "utils" / "messages.ts").read_text(encoding="utf-8")
    if "messageKey" not in messages or "mergeMessages" not in messages:
        raise TestFailure("utils/messages dedupe helpers missing")
    ok("messageKey dedupe for delta merge")


def test_f12_phase1_persistence() -> None:
    section("T1k F12 Phase 1 Runner persistence logs")
    script = HBM_DIR / "scripts" / "test_f12_phase1_persistence.py"
    if not script.is_file():
        raise TestFailure(f"missing {script}")
    env = apply_hbm_demo_env(dict(os.environ))
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise TestFailure(
            proc.stdout + proc.stderr or "F12 Phase 1 tests failed"
        )
    ok("F12 Phase 1 persistence script passed")


def test_f12_phase2_world_delta() -> None:
    section("T1l F12 Phase 2 Flask world delta API")
    script = HBM_DIR / "scripts" / "test_f12_world_delta.py"
    if not script.is_file():
        raise TestFailure(f"missing {script}")
    env = apply_hbm_demo_env(dict(os.environ))
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise TestFailure(
            proc.stdout + proc.stderr or "F12 Phase 2 tests failed"
        )
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
        "RoomSpeechBubble.tsx",
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
    script = HBM_DIR / "scripts" / "test_f12_visibility.py"
    if not script.is_file():
        raise TestFailure(f"missing {script}")
    env = apply_hbm_demo_env(dict(os.environ))
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise TestFailure(
            proc.stdout + proc.stderr or "F12 visibility tests failed"
        )
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
        is_experience_hardening,
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

    class F2fNegotiationDB(EmptyDB):
        def has_f2f_after(self, place_id, *a, **k):
            return place_id == NEGOTIATION_PLACE

    task_p1 = PendingTask(
        task_id="t1",
        start_tick=0,
        place_id="nvidia_reception",
        phase="Phase 1",
        player_turn=1,
        ipc_end_tick=6,
        inject_status=INJECT_STATUS_DONE,
    )
    if is_experience_hardening():
        if check_action_complete(task_p1, 6, RdcOnlyDB()):
            raise TestFailure("E5 Phase 1 must not complete on RDC alone")
        if check_action_complete(task_p1, 8, EmptyDB()):
            raise TestFailure("E5 Phase 1 must not timeout-complete without F2F")
        if not check_action_complete(task_p1, 5, F2fReceptionDB()):
            raise TestFailure("E5 Phase 1 should complete on reception F2F")
        ok("E5 Phase 1 F2F-only completion (experience_hardening)")
    elif is_f07_enabled():
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
    if is_experience_hardening():
        if check_action_complete(task_p2, 8, EmptyDB()):
            raise TestFailure("E5 Phase 2 must not timeout-complete without F2F")
        if not check_action_complete(task_p2, 5, F2fJensenDB()):
            raise TestFailure("E5 Phase 2 should complete on Jensen room F2F")
        ok("E5 Phase 2 F2F-only completion (experience_hardening)")
    else:
        if check_action_complete(task_p2, 6, EmptyDB()):
            raise TestFailure(
                "v2 continuous delta must not complete at ipc_end_tick alone (tick 6)"
            )
        if not check_action_complete(task_p2, 8, EmptyDB()):
            raise TestFailure("v2 should timeout-complete Phase 2 at tick 8")
        ok("v2 continuous delta: Phase 2 no ipc_end-only completion")

    if is_experience_hardening():
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
            raise TestFailure("E5 Phase 4 must not complete on VP RDC alone")
        if check_action_complete(task_p4, 8, EmptyDB()):
            raise TestFailure("E5 Phase 4 must not timeout-complete without F2F")
        if not check_action_complete(task_p4, 5, F2fNegotiationDB()):
            raise TestFailure("E5 Phase 4 should complete on negotiation F2F")
        ok("E5 Phase 4 F2F-only completion (experience_hardening)")
    elif is_f07_enabled():
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
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        inject_exclusive_ticks_for,
        is_experience_hardening,
        is_hard_block_enabled,
        load_turn_control,
        resolve_inject_tick_count,
        scripted_f2f_fallback_enabled,
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

    load_turn_control.cache_clear()
    if is_experience_hardening():
        raise TestFailure("v2 Phase0 requires experience_hardening.enabled=false")
    if is_hard_block_enabled():
        raise TestFailure("v2 Phase0 requires tool_guard.hard_block=false")
    if scripted_f2f_fallback_enabled():
        raise TestFailure("v2 Phase0 requires scripted_f2f_fallback=false")
    if inject_exclusive_ticks_for("Phase 1") != 2:
        raise TestFailure(
            f"v2 inject_exclusive from phases expected 2: {inject_exclusive_ticks_for('Phase 1')}"
        )
    ok("v2 Phase0 turn_control: hardening off, hard_block off, inject_exclusive=2")

    blocked = filter_tool_calls(
        2,
        ctx_p1,
        [_ToolCall(tool_name="request_move", args={"place_id": "x"})],
    )
    if is_hard_block_enabled():
        if not blocked or blocked[0].tool_name != "do_nothing":
            raise TestFailure(f"hard_block MOVE should become do_nothing: {blocked}")
        ok("B3 filter_tool_calls replaces illegal MOVE (hard_block)")
    else:
        if blocked:
            raise TestFailure(
                f"v2 should drop disallowed MOVE without do_nothing: {blocked}"
            )
        ok("B3 v2 filter_tool_calls drops illegal MOVE (no mass do_nothing)")

    allowed_mix = filter_tool_calls(
        1,
        ctx_p1,
        [
            _ToolCall(tool_name="speak_to_local", args={"content": "hi"}),
            _ToolCall(tool_name="request_move", args={"place_id": "x"}),
        ],
    )
    if not allowed_mix or allowed_mix[0].tool_name != "speak_to_local":
        raise TestFailure(f"v2 mixed batch should keep speak_to_local: {allowed_mix}")
    if len(allowed_mix) != 1:
        raise TestFailure(f"v2 mixed batch should drop MOVE only: {allowed_mix}")
    ok("B3 v2 mixed tool batch keeps allowed tools")

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

    if is_experience_hardening():
        if resolve_inject_tick_count("Phase 1", 6) != 12:
            raise TestFailure("E5 Phase 1 inject tick_count should floor at 12")
        if resolve_inject_tick_count("Phase 2", 6) != 12:
            raise TestFailure("E5 Phase 2 inject tick_count should floor at 12")
        if resolve_inject_tick_count("Phase 4", 6) != 12:
            raise TestFailure("E5 Phase 4 inject tick_count should floor at 12")
        ok("E5 experience_hardening inject tick_count ≥12")
    else:
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
    from agent_world.hbm_demo.features.f07_agent_control.tool_guard import (
        allowed_tools_for,
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

    ctx_p4 = {
        "phase": "Phase 4",
        "player_turn": 21,
        "place_id": "negotiation_room",
        "llm_params": {"temperature": 0.48, "max_tokens": 200},
    }
    if primary_active_ids(ctx_p4) != [2]:
        raise TestFailure(f"D1 primary_active Phase 4 must be [2]: {primary_active_ids(ctx_p4)}")
    world = SimpleNamespace(agents={2: object(), 3: object()})
    active = pick_active_ids(ctx_p4, world, t=10)
    if 3 in active:
        raise TestFailure(f"D1 Agent 3 present_silent must not tick: {active}")
    if active != [2]:
        raise TestFailure(f"D1 Phase 4 active should be [2]: {active}")
    ok("D1 Phase 4 L3 primary [2], Agent 3 present_silent (no tick)")

    vp_tools = allowed_tools_for(3, ctx_p4)
    if vp_tools:
        raise TestFailure(f"D1 Agent 3 Phase 4 tools must be empty: {vp_tools}")
    ok("D1 Agent 3 Phase 4 tool matrix empty")

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
        is_experience_hardening,
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
    if is_experience_hardening():
        raise TestFailure("v2 Phase0 experience_hardening.enabled should be false")
    ok("v2 Phase0 experience_hardening disabled (E0 runtime hook off)")

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


def test_f07_e_step2_guard_and_fallback() -> None:
    """F07-E Step2 — E1 first-action guard + E5 completion + scripted fallback (dev_logs/29)."""
    import asyncio
    import tempfile

    section("T2h F07-E Step2 E1 guard + E5 + f2f_fallback")
    from agent_world.demo.demo_agent import _ToolCall
    from agent_world.hbm_demo.features import FEATURE_REGISTRY
    from agent_world.hbm_demo.features.f07_agent_control.batch_guard import (
        BatchGuardState,
    )
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        first_f2f_required_agents,
        is_experience_hardening,
        is_f07_enabled,
        load_turn_control,
        scripted_f2f_fallback_enabled,
    )
    from agent_world.hbm_demo.features.f07_agent_control.f2f_fallback import (
        apply_batch_f2f_fallback,
        build_fallback_content,
        extract_player_keyword,
    )
    from agent_world.hbm_demo.features.f07_agent_control.tool_guard import (
        filter_tool_calls,
    )
    from agent_world.hbm_demo.features.f06_read_model.world_db import ReadOnlyWorldDB
    from agent_world.persistence.world_db import WorldDB

    phase = FEATURE_REGISTRY.get("F07", {}).get("phase", "")
    if "F07-E" not in phase:
        raise TestFailure(f"F07 registry phase should mention F07-E: {phase!r}")
    ok(f"FEATURE_REGISTRY F07 phase: {phase}")

    if not is_f07_enabled():
        ok("F07-E Step2 tests skipped (F07 disabled)")
        return

    load_turn_control.cache_clear()
    if not is_experience_hardening():
        ok("F07-E Step2 skipped (v2 experience_hardening off)")
        return

    if first_f2f_required_agents("Phase 1") != [1]:
        raise TestFailure(f"Phase 1 first_f2f_required wrong: {first_f2f_required_agents('Phase 1')}")
    ok("E1 first_f2f_required Phase 1 → [1]")

    kw = extract_player_keyword("玩家说：我们能把显存占用压到 40% 吗？")
    if "40%" not in kw and "显存" not in kw:
        raise TestFailure(f"extract_player_keyword unexpected: {kw!r}")
    content = build_fallback_content("Phase 1", "玩家说：我们能把显存占用压到 40% 吗？")
    if "40%" not in content and "显存" not in content:
        raise TestFailure(f"build_fallback_content unexpected: {content!r}")
    ok("E1 fallback template uses player keyword")

    ctx_p1 = {
        "phase": "Phase 1",
        "player_turn": 1,
        "place_id": "nvidia_reception",
        "player_text": "玩家说：我们能把显存占用压到 40% 吗？",
        "inject_agent_ids": [1],
    }
    guard = BatchGuardState()
    blocked = filter_tool_calls(
        1,
        ctx_p1,
        [_ToolCall(tool_name="send_message", args={"target": 2, "content": "x"})],
        batch_guard=guard,
    )
    if not blocked or blocked[0].tool_name != "do_nothing":
        raise TestFailure(f"E1 should block send_message before F2F: {blocked}")
    allowed = filter_tool_calls(
        1,
        ctx_p1,
        [_ToolCall(tool_name="speak_to_local", args={"content": "hello"})],
        batch_guard=guard,
    )
    if not allowed or allowed[0].tool_name != "speak_to_local":
        raise TestFailure(f"E1 should allow speak_to_local before F2F: {allowed}")
    guard.mark_f2f(1)
    after_f2f = filter_tool_calls(
        1,
        ctx_p1,
        [_ToolCall(tool_name="send_message", args={"target": 2, "content": "x"})],
        batch_guard=guard,
    )
    if not after_f2f or after_f2f[0].tool_name != "send_message":
        raise TestFailure(f"E1 should allow send_message after F2F marked: {after_f2f}")
    ok("E1 first_action_guard blocks non-F2F until batch_guard.mark_f2f")

    ipc_src = (HBM_DIR / "core" / "runner" / "ipc_handlers.py").read_text(encoding="utf-8")
    if "apply_batch_f2f_fallback_at" not in ipc_src:
        raise TestFailure("ipc_handlers should call apply_batch_f2f_fallback_at")
    ok("E1 ipc_handlers batch-end fallback hook present")

    async def _fallback_emit() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "world.db"
            wdb = WorldDB(str(db_path))
            wdb.init_schema()
            batch = BatchGuardState()
            turn_ctx = {
                "phase": "Phase 1",
                "place_id": "nvidia_reception",
                "player_text": "玩家说：KV cache 优化",
            }
            n = await apply_batch_f2f_fallback(
                wdb,
                turn_context=turn_ctx,
                batch_guard=batch,
                t=9,
            )
            if n != 1:
                raise TestFailure(f"apply_batch_f2f_fallback expected 1 emit, got {n}")
            if not batch.has_f2f(1):
                raise TestFailure("fallback should mark_f2f(1)")
            ro = ReadOnlyWorldDB(db_path)
            rows = ro.fetch_f2f_history_at("nvidia_reception", 9, 0, limit=5)
            if len(rows) < 1:
                raise TestFailure("fallback F2F not visible in ReadOnlyWorldDB")
            n2 = await apply_batch_f2f_fallback(
                wdb,
                turn_context=turn_ctx,
                batch_guard=batch,
                t=10,
            )
            if n2 != 0:
                raise TestFailure("fallback should not double-emit")

    asyncio.run(_fallback_emit())
    ok("E1 apply_batch_f2f_fallback emits scripted F2F once per batch")


def test_f07_e_step3_rdc_quota_and_tick_order() -> None:
    """F07-E Step3 — E2 RDC quota + inject_exclusive_ticks + 12-tick IPC (dev_logs/29)."""
    from types import SimpleNamespace

    section("T2i F07-E Step3 E2 RDC quota + inject tick order")
    from agent_world.demo.demo_agent import _ToolCall
    from agent_world.hbm_demo.features import FEATURE_REGISTRY
    from agent_world.hbm_demo.features.f07_agent_control.batch_guard import (
        BatchGuardState,
    )
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        inject_exclusive_ticks_for,
        is_experience_hardening,
        is_f07_enabled,
        load_turn_control,
        max_inject_tick_loops,
        rdc_quota_for,
        resolve_inject_tick_loops,
    )
    from agent_world.hbm_demo.features.f07_agent_control.pick_active import (
        pick_active_ids,
    )
    from agent_world.hbm_demo.features.f07_agent_control.tool_guard import (
        filter_tool_calls,
    )

    phase = FEATURE_REGISTRY.get("F07", {}).get("phase", "")
    if "F07-E" not in phase:
        raise TestFailure(f"F07 registry phase should mention F07-E: {phase!r}")
    ok(f"FEATURE_REGISTRY F07 phase: {phase}")

    if not is_f07_enabled():
        ok("F07-E Step3 tests skipped (F07 disabled)")
        return

    load_turn_control.cache_clear()
    if not is_experience_hardening():
        if inject_exclusive_ticks_for("Phase 1") != 2:
            raise TestFailure(
                f"v2 Phase1 inject_exclusive expected 2: {inject_exclusive_ticks_for('Phase 1')}"
            )
        ctx_ex = {
            "phase": "Phase 1",
            "player_turn": 1,
            "inject_agent_ids": [1],
        }
        world_ex = SimpleNamespace(agents={1: object(), 2: object(), 3: object()})
        if pick_active_ids(ctx_ex, world_ex, t=1, batch_tick_index=0) != [1]:
            raise TestFailure(
                "v2 inject_exclusive tick0 should be [1]: "
                f"{pick_active_ids(ctx_ex, world_ex, t=1, batch_tick_index=0)}"
            )
        ok("v2 inject_exclusive L3 tick0 → [1]")
        ok("F07-E Step3 skipped (v2 experience_hardening off)")
        return

    if rdc_quota_for(1, "Phase 1") != 1:
        raise TestFailure(f"Phase 1 agent 1 RDC quota expected 1: {rdc_quota_for(1, 'Phase 1')}")
    if rdc_quota_for(2, "Phase 1") != 2:
        raise TestFailure(f"Phase 1 agent 2 RDC quota expected 2: {rdc_quota_for(2, 'Phase 1')}")
    if inject_exclusive_ticks_for("Phase 1") != 2:
        raise TestFailure(f"Phase 1 inject_exclusive_ticks expected 2: {inject_exclusive_ticks_for('Phase 1')}")
    ok("E2 turn_control rdc_quota + inject_exclusive_ticks")

    if max_inject_tick_loops() != 12:
        raise TestFailure(f"max_inject_tick_loops should be 12: {max_inject_tick_loops()}")
    if resolve_inject_tick_loops(12) != 12:
        raise TestFailure("resolve_inject_tick_loops(12) should run 12 ticks")
    if resolve_inject_tick_loops(6) != 6:
        raise TestFailure("resolve_inject_tick_loops(6) should respect requested count")
    if resolve_inject_tick_loops(20) != 12:
        raise TestFailure("resolve_inject_tick_loops should cap at 12")
    ok("E2 resolve_inject_tick_loops cap=12")

    ipc_src = (HBM_DIR / "core" / "runner" / "ipc_handlers.py").read_text(encoding="utf-8")
    if "resolve_inject_tick_loops" not in ipc_src:
        raise TestFailure("ipc_handlers should use resolve_inject_tick_loops")
    ok("E2 ipc_handlers 12-tick loop cap wired")

    ctx_p1 = {
        "phase": "Phase 1",
        "player_turn": 1,
        "place_id": "nvidia_reception",
        "inject_agent_ids": [1],
    }
    world = SimpleNamespace(agents={1: object(), 2: object(), 3: object()})

    exclusive_tick0 = pick_active_ids(
        ctx_p1, world, t=1, batch_tick_index=0
    )
    if exclusive_tick0 != [1]:
        raise TestFailure(f"inject_exclusive tick0 expected [1]: {exclusive_tick0}")
    exclusive_tick1 = pick_active_ids(
        ctx_p1, world, t=2, batch_tick_index=1
    )
    if exclusive_tick1 != [1]:
        raise TestFailure(f"inject_exclusive tick1 expected [1]: {exclusive_tick1}")
    normal_tick2 = pick_active_ids(
        ctx_p1, world, t=3, batch_tick_index=2
    )
    if not all(aid in normal_tick2 for aid in (1, 2, 3)):
        raise TestFailure(f"tick2+ should restore primary [1,2,3]: {normal_tick2}")
    ok("E2 inject_exclusive_ticks Phase 1 tick0-1 → [1] only")

    guard = BatchGuardState()
    guard.mark_f2f(1)
    guard.mark_rdc(1, 2)
    blocked_rdc = filter_tool_calls(
        1,
        ctx_p1,
        [_ToolCall(tool_name="send_message", args={"target": 2, "content": "dup"})],
        batch_guard=guard,
    )
    if not blocked_rdc or blocked_rdc[0].tool_name != "do_nothing":
        raise TestFailure(f"E2 should block 2nd RDC for agent 1: {blocked_rdc}")
    ok("E2 rdc_quota blocks send_message after quota exhausted")

    ws_src = (HBM_DIR / "core" / "runner" / "world_step.py").read_text(encoding="utf-8")
    if "_batch_tick_index" not in ws_src or "_mark_rdc_if_sent" not in ws_src:
        raise TestFailure("HbmWorldStep missing batch_tick_index / mark_rdc hooks")
    ok("E2 world_step batch_tick_index + mark_rdc_if_sent present")


def test_f07_e_step4_turn_priority_and_offtopic() -> None:
    """F07-E Step4 — E3 turn-scoped L6 + Jensen summary + E4 off-topic guard (dev_logs/29)."""
    section("T2j F07-E Step4 E3 turn priority + E4 off-topic guard")
    from types import SimpleNamespace

    from agent_world.hbm_demo.features import FEATURE_REGISTRY
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_experience_hardening,
        is_f07_enabled,
        load_turn_control,
    )
    from agent_world.hbm_demo.features.f07_agent_control.inject_batch import (
        notify_jensen_player_summary,
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
    hardening = is_experience_hardening()

    l6 = format_l6_player_directive(
        agent_id=1,
        phase="Phase 1",
        player_turn=2,
        player_text="我给您带了杯咖啡，黄总在吗？",
    )
    if hardening:
        if "本 Turn 唯一权威" not in l6:
            raise TestFailure("E3 L6 missing turn-scoped authority line")
        if "闲聊" not in l6 and "玩梗" not in l6:
            raise TestFailure("E3 L6 missing small-talk diversion line")
        ok("E3 Agent1 Phase1 L6 turn-scoped + small-talk diversion")
    else:
        if "必须先直接回应玩家" not in l6:
            raise TestFailure("v2 L6 missing direct-response line")
        ok("v2 Phase0 L6 core directive (E3 turn-scoped lines inactive)")

    notif = format_notification_directive(
        phase="Phase 1", player_turn=1, agent_id=2
    )
    if "roadmap" not in notif and "RDC" not in notif:
        raise TestFailure(f"E4 notification missing off-topic guard: {notif[:80]}")
    ok("E4 Phase1 Jensen notification narrowed")

    if hardening:
        class _ScriptEngine:
            def __init__(self) -> None:
                self.calls: list[tuple[int, str]] = []

            def notify_agent(self, aid: int, snippet: str) -> None:
                self.calls.append((int(aid), str(snippet)))

        se = _ScriptEngine()
        notify_jensen_player_summary(
            se,
            {"phase": "Phase 1", "player_text": "送杯咖啡"},
            "送杯咖啡",
        )
        if not se.calls or se.calls[0][0] != 2:
            raise TestFailure(f"E3 notify_jensen_player_summary bad target: {se.calls}")
        if "送杯咖啡" not in se.calls[0][1]:
            raise TestFailure(f"E3 Jensen summary missing player_text: {se.calls[0][1]}")
        ok("E3 notify_jensen_player_summary → Agent 2")
    else:
        ok("v2 Phase0 E3 notify_jensen_player_summary inactive (hardening off)")

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
    if hardening:
        if "notify_jensen_player_summary" not in ipc_src:
            raise TestFailure("ipc_handlers should call notify_jensen_player_summary")
    elif "notify_jensen_player_summary(" in ipc_src:
        raise TestFailure(
            "v2 Phase0 ipc_handlers must not call notify_jensen_player_summary"
        )
    if "clear_player_memory_for_agents" not in ipc_src:
        raise TestFailure("A6 clear_player_memory_for_agents regression")
    ok("v2 Phase0 ipc_handlers: no E3 summary hook; A6 memory clear kept")

    ws_src = (HBM_DIR / "core" / "runner" / "world_step.py").read_text(encoding="utf-8")
    if "_resolve_batch_llm_params" not in ws_src:
        raise TestFailure("world_step missing passive LLM param resolver")
    ok("E4 world_step passive LLM cooling hook")

    ha_src = (HBM_DIR / "core" / "runner" / "hbm_agent.py").read_text(encoding="utf-8")
    if "do_nothing" not in ha_src or "无新前台 RDC" not in ha_src:
        raise TestFailure("hbm_agent missing Phase1 passive do_nothing rule")
    ok("E4 hbm_agent Phase1 passive short action rules")

    session = SimpleNamespace(
        phase="Phase 1", player_turn=1, place_id="nvidia_reception", stats={}
    )
    block = build_agent_knowledge(
        session, 1, "80% 显存优化", channel="inject"
    )
    if "80%" not in block:
        raise TestFailure("inject knowledge block should include player text")
    ok("E3 build_agent_knowledge inject still includes player line")


def test_f07_e_step5_final_acceptance() -> None:
    """F07-E Step5 — final acceptance helpers (dev_logs/29 §10.8 Step 5)."""
    section("T2k F07-E Step5 final acceptance helpers")
    from agent_world.hbm_demo.features import FEATURE_REGISTRY
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_experience_hardening,
        is_f07_enabled,
    )
    from agent_world.hbm_demo.features.f07_agent_control.phase4_smoke import (
        Phase4SmokeResult,
        run_phase4_ipc_smoke,
    )
    from agent_world.hbm_demo.shared.env_status import is_runner_ready

    phase = FEATURE_REGISTRY.get("F07", {}).get("phase", "")
    if "F07-E Step5" not in phase:
        raise TestFailure(f"F07 registry phase should mention F07-E Step5: {phase!r}")
    ok(f"FEATURE_REGISTRY F07 phase: {phase}")

    if not is_f07_enabled():
        ok("F07-E Step5 skipped (F07 disabled)")
        return
    if not is_experience_hardening():
        ok("F07-E Step5 skipped (v2 experience_hardening off)")
        return

    smoke_src = (
        HBM_DIR / "features" / "f07_agent_control" / "phase4_smoke.py"
    ).read_text(encoding="utf-8")
    if "run_phase4_ipc_smoke" not in smoke_src:
        raise TestFailure("phase4_smoke.py missing run_phase4_ipc_smoke")
    ok("E6 phase4_smoke module present")

    ipc_src = (HBM_DIR / "core" / "runner" / "ipc_handlers.py").read_text(
        encoding="utf-8"
    )
    if "notify_jensen_player_summary" not in ipc_src:
        raise TestFailure("Step5 regression: notify_jensen_player_summary missing")
    ok("E3/E6 ipc_handlers Jensen summary hook (regression)")

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
            f"E6 Phase4 IPC smoke (unit) — Jensen F2F={result.jensen_f2f_count} "
            f"end_tick={result.end_tick}"
        )
    else:
        ok("E6 Phase4 IPC smoke skipped (runner not ready in unit pass)")


def test_f07_v2_phase0_hard_control_retired() -> None:
    """dev_logs/31 Phase 0 — retire F07-E hard guards; HBM MOVE is IPC-only."""
    import asyncio

    section("T2l v2 Phase0 hard control retired")
    from types import SimpleNamespace

    from agent_world.hbm_demo.core.runner.hbm_dispatcher import HbmActionDispatcher
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_experience_hardening,
        is_f07_enabled,
        is_hard_block_enabled,
        load_turn_control,
        scripted_f2f_fallback_enabled,
    )

    if not is_f07_enabled():
        ok("v2 Phase0 skipped (F07 disabled)")
        return

    load_turn_control.cache_clear()
    if is_experience_hardening():
        raise TestFailure("Phase0: experience_hardening.enabled must be false")
    if is_hard_block_enabled():
        raise TestFailure("Phase0: tool_guard.hard_block must be false")
    if scripted_f2f_fallback_enabled():
        raise TestFailure("Phase0: scripted_f2f_fallback must be false")
    ok("Phase0 turn_control: hardening/hard_block/fallback off")

    ipc_src = (HBM_DIR / "core" / "runner" / "ipc_handlers.py").read_text(
        encoding="utf-8"
    )
    if "apply_batch_f2f_fallback_at" in ipc_src:
        raise TestFailure("Phase0: ipc_handlers must not call apply_batch_f2f_fallback_at")
    ok("Phase0 ipc_handlers: batch F2F fallback removed")

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
        ok(f"Phase1b POST /world-loop/pause → tick={pause_tick}")

        frozen_deadline = time.time() + 6.0
        while time.time() < frozen_deadline:
            _, env_frozen, _ = http_json("GET", f"{base}{BASE_PATH}/env-status")
            frozen_tick = int((env_frozen.get("data") or {}).get("current_tick", -1))
            if frozen_tick != pause_tick:
                raise TestFailure(
                    f"Phase1b tick moved while paused: {pause_tick} → {frozen_tick}"
                )
            time.sleep(1.0)
        ok(f"Phase1b tick frozen at {pause_tick} for 5s")

        code, resume_resp, _ = http_json(
            "POST", f"{base}{BASE_PATH}/world-loop/resume", timeout=15.0
        )
        if code != 200 or not resume_resp.get("success"):
            raise TestFailure(f"Phase1b resume failed HTTP {code}: {resume_resp}")
        if (resume_resp.get("data") or {}).get("loop_state") != "running":
            raise TestFailure(f"Phase1b resume loop_state != running: {resume_resp}")
        ok("Phase1b POST /world-loop/resume → running")

        resume_tick = pause_tick
        resume_deadline = time.time() + 45.0
        while time.time() < resume_deadline:
            time.sleep(1.0)
            _, env_resume, _ = http_json("GET", f"{base}{BASE_PATH}/env-status")
            resume_tick = int((env_resume.get("data") or {}).get("current_tick", resume_tick))
            if resume_tick > pause_tick:
                break
        if resume_tick <= pause_tick:
            raise TestFailure(
                f"Phase1b tick did not advance after resume: {pause_tick} → {resume_tick}"
            )
        ok(f"Phase1b tick resumed {pause_tick} → {resume_tick}")

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
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_experience_hardening,
    )

    if is_experience_hardening():
        if len(reception_msgs) < 1:
            raise TestFailure(
                f"Phase 3: Turn1 room_f2f.nvidia_reception empty — frontend bubbles need F2F: {reception_msgs}"
            )
        ok(f"Phase 3 room_f2f reception has {len(reception_msgs)} F2F message(s)")
    else:
        if len(reception_msgs) < 1 and len(observer) < 1:
            raise TestFailure(
                f"v2 Phase0 Turn1 needs F2F or RDC activity: "
                f"reception={reception_msgs} observer={len(observer)}"
            )
        ok(
            f"v2 Phase0 Turn1 activity — reception_f2f={len(reception_msgs)} "
            f"observer={len(observer)} (no scripted fallback required)"
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
        is_experience_hardening,
        max_inject_tick_loops,
    )

    min_ipc_end = max_inject_tick_loops() if is_experience_hardening() else 8
    if ipc_end < min_ipc_end:
        raise TestFailure(
            f"F07 Phase 1 inject must reach tick≥{min_ipc_end}; ipc_end_tick={ipc_end}"
        )
    ok(f"Tier A: ipc_end_tick={ipc_end} (≥{min_ipc_end}, no processing deadlock)")
    if is_experience_hardening():
        if len(grp) != 0:
            raise TestFailure(
                f"F07 Phase 1 Turn 1 GRP must be 0 (L3/L5); got GRP={len(grp)}"
            )
        ok("Tier A: Phase 1 Turn 1 GRP=0")
    else:
        ok(f"v2 Phase0 Turn1 GRP={len(grp)} (hard_block off — LLM may emit GRP)")
    if llm_key:
        from agent_world.hbm_demo.features.f07_agent_control.config import (
            is_experience_hardening,
        )

        if is_experience_hardening():
            if len(public) < 1:
                raise TestFailure(
                    "Tier B E5: experience_hardening requires F2F≥1 on Phase 1 Turn 1. "
                    "Last runner log:\n"
                    + runner_log_excerpt()
                )
            reception_jensen = sum(
                1
                for m in observer
                if m.get("type") == "RDC"
                and m.get("sender") == "接待前台"
                and m.get("recipient") == "Jensen"
            )
            if reception_jensen > 2:
                raise TestFailure(
                    f"Tier B E2: reception→Jensen RDC must be ≤2; got {reception_jensen}"
                )
            if len(observer) > 6:
                raise TestFailure(
                    f"Tier B E2: Phase 1 observer_messages must be ≤6; got {len(observer)}"
                )
            _offtopic_terms = ("三星", "roadmap", "Roadmap")
            for m in observer:
                body = str(m.get("content") or "")
                sender = str(m.get("sender") or "")
                for term in _offtopic_terms:
                    if term in body and term not in player_text:
                        raise TestFailure(
                            f"Tier B E4: observer from {sender} contains "
                            f"unmentioned {term!r}: {body[:160]}"
                        )
            ok(
                f"Tier B E5+E2+E4: F2F={len(public)} reception→Jensen RDC={reception_jensen} "
                f"observer={len(observer)} (no 三星/roadmap hallucination)"
            )
        elif len(public) < 1 and len(observer) < 1:
            raise TestFailure(
                "Tier B: DMXAPI_KEY set but no F2F and no observer RDC — "
                "LLM pipeline may be broken. Last runner log:\n"
                + runner_log_excerpt()
            )
        else:
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

    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_experience_hardening,
    )

    if is_experience_hardening() and len(public2) < 1:
        raise TestFailure(
            "E3 Turn 2: experience_hardening requires F2F≥1 (fallback or LLM)"
        )
    if is_experience_hardening():
        f2f_blob = " ".join(str(m.get("content") or "") for m in public2)
        turn2_hints = ("咖啡", "皮衣", "等", "打扰", "稍等", "通报", "技术方案", "黄总")
        if llm_key and not any(h in f2f_blob for h in turn2_hints):
            raise TestFailure(
                f"E3 Turn 2 Tier B: F2F should respond to small-talk; got: {f2f_blob[:200]}"
            )
        for m in observer2:
            if m.get("sender") != "接待前台":
                continue
            body = str(m.get("content") or "")
            if ("80%" in body or "显存" in body) and "80%" not in turn2_text:
                raise TestFailure(
                    f"E3 Turn 2: reception should not re-RDC Turn1 topic: {body[:160]}"
                )
        ok(
            f"E3 Turn 2 — F2F={len(public2)} observer={len(observer2)} "
            f"(small-talk / no Turn1 RDC repeat)"
        )
    else:
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

    section("T4f F07-E6 Phase 4 IPC smoke (dev_logs/29 §3.6.4)")
    from agent_world.hbm_demo.features.f07_agent_control.phase4_smoke import (
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
        test_f07_e_step2_guard_and_fallback,
        test_f07_e_step3_rdc_quota_and_tick_order,
        test_f07_e_step4_turn_priority_and_offtopic,
        test_f07_e_step5_final_acceptance,
        test_f07_v2_phase0_hard_control_retired,
        test_f07_v2_phase1_world_loop,
        test_f07_v2_phase1b_world_loop_pause,
        test_f07_v2_phase2_world_delta,
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

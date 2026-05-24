#!/usr/bin/env python3
"""M0–M5 acceptance tests — dev_logs/26 §7."""

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


class TestFailure(Exception):
    pass


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


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

    if len(FEATURE_REGISTRY) < 11:
        raise TestFailure(f"FEATURE_REGISTRY expected >=11, got {len(FEATURE_REGISTRY)}")
    ok(f"FEATURE_REGISTRY: {len(FEATURE_REGISTRY)} features")

    import agent_world.hbm_demo.routing as root_routing
    from agent_world.hbm_demo.features.f05_story_routing import routing as feat_routing

    if root_routing.apply_routing is not feat_routing.apply_routing:
        raise TestFailure("routing shim does not re-export f05.apply_routing")
    ok("routing.py shim → features/f05_story_routing")

    import agent_world.hbm_demo.world_reset as root_wr
    from agent_world.hbm_demo.features.f01_session import world_reset as feat_wr

    if root_wr.reset_world_runtime is not feat_wr.reset_world_runtime:
        raise TestFailure("world_reset shim does not re-export f01.reset_world_runtime")
    ok("world_reset.py shim → features/f01_session")

    from agent_world.hbm_demo import game_service as gs
    from agent_world.hbm_demo import routing

    if routing.inject_agent_ids_for_phase("Phase 1") != [1]:
        raise TestFailure("F05 Phase 1 inject agents != [1]")
    ok("F05 inject_agent_ids_for_phase Phase 1 → [1]")

    if not hasattr(gs, "handle_player_turn") or not hasattr(gs, "reset_demo"):
        raise TestFailure("game_service missing handle_player_turn or reset_demo")
    ok("game_service orchestration entrypoints present")

    from agent_world.hbm_demo.ipc_handlers import wire_handlers  # noqa: F401

    ok("ipc_handlers imports (uses world_reset shim)")


def test_m1_shared_shims() -> None:
    section("T1b M1 shared/ 模块与根 shim")
    import agent_world.hbm_demo.env_status as root_es
    import agent_world.hbm_demo.settings as root_st
    import agent_world.hbm_demo.errors as root_er
    import agent_world.hbm_demo.config_loader as root_cl
    from agent_world.hbm_demo import shared
    from agent_world.hbm_demo.shared import env_status as shared_es
    from agent_world.hbm_demo.shared import settings as shared_st
    from agent_world.hbm_demo.shared import errors as shared_er
    from agent_world.hbm_demo.shared import config_loader as shared_cl

    pairs = (
        ("env_status.is_runner_ready", root_es.is_runner_ready, shared_es.is_runner_ready),
        ("env_status.write_env_status", root_es.write_env_status, shared_es.write_env_status),
        ("settings.DEFAULT_IPC_TIMEOUT", root_st.DEFAULT_IPC_TIMEOUT, shared_st.DEFAULT_IPC_TIMEOUT),
        ("errors.RunnerNotReadyError", root_er.RunnerNotReadyError, shared_er.RunnerNotReadyError),
        ("config_loader.load_scenario", root_cl.load_scenario, shared_cl.load_scenario),
    )
    for name, root_fn, shared_fn in pairs:
        if root_fn is not shared_fn:
            raise TestFailure(f"{name} shim != shared implementation")
        ok(f"{name}")

    scenario = shared.load_scenario(HBM_DIR / "hbm_scenario.yaml")
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


def test_m3_runner_shims() -> None:
    section("T1d M3 core/runner/ 模块与根 shim")
    import agent_world.hbm_demo.kernel as root_kernel
    import agent_world.hbm_demo.ipc_handlers as root_ipc
    import agent_world.hbm_demo.hbm_agent as root_agent
    import agent_world.hbm_demo.run_hbm as root_run
    from agent_world.hbm_demo.core.runner import kernel as core_kernel
    from agent_world.hbm_demo.core.runner import ipc_handlers as core_ipc
    from agent_world.hbm_demo.core.runner import hbm_agent as core_agent
    from agent_world.hbm_demo.core.runner import run_hbm as core_run

    pairs = (
        ("kernel.build_kernel", root_kernel.build_kernel, core_kernel.build_kernel),
        ("kernel.resolve_api_key", root_kernel.resolve_api_key, core_kernel.resolve_api_key),
        ("ipc_handlers.wire_handlers", root_ipc.wire_handlers, core_ipc.wire_handlers),
        ("hbm_agent.HbmAgent", root_agent.HbmAgent, core_agent.HbmAgent),
        ("run_hbm.main", root_run.main, core_run.main),
    )
    for name, root_fn, core_fn in pairs:
        if root_fn is not core_fn:
            raise TestFailure(f"{name} shim != core/runner implementation")
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


def test_m4_http_shims() -> None:
    section("T1e M4 http/ 模块与根 shim")
    import agent_world.hbm_demo.routes as root_routes
    import agent_world.hbm_demo.ipc_helper as root_ipc
    import agent_world.hbm_demo.health as root_health
    import agent_world.hbm_demo.http_errors as root_errors
    from agent_world.hbm_demo.http import routes as http_routes
    from agent_world.hbm_demo.http import ipc_helper as http_ipc
    from agent_world.hbm_demo.http import health as http_health
    from agent_world.hbm_demo.http import http_errors as http_err

    pairs = (
        ("routes.hbm_bp", root_routes.hbm_bp, http_routes.hbm_bp),
        ("ipc_helper.send_inject_batch", root_ipc.send_inject_batch, http_ipc.send_inject_batch),
        ("health.check_stack_health", root_health.check_stack_health, http_health.check_stack_health),
        ("http_errors.service_error_payload", root_errors.service_error_payload, http_err.service_error_payload),
    )
    for name, root_obj, http_obj in pairs:
        if root_obj is not http_obj:
            raise TestFailure(f"{name} shim != http implementation")
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


def test_m5_f07_abcs() -> None:
    section("T1f M5 F07 ABCS turn control")
    from agent_world.demo.demo_agent import _ToolCall
    from agent_world.hbm_demo.features.f07_agent_control.matrix import (
        allowed_tools_for,
        is_move_allowed,
        resolve_active_agent_ids,
    )
    from agent_world.hbm_demo.features.f07_agent_control.tool_guard import filter_tool_calls
    from agent_world.hbm_demo.features.f07_agent_control.turn_context import (
        build_turn_context,
        format_constraint_prefix,
    )
    import agent_world.hbm_demo.turn_context as root_tc
    from agent_world.hbm_demo.features.f07_agent_control import turn_context as feat_tc

    if root_tc.build_turn_context is not feat_tc.build_turn_context:
        raise TestFailure("turn_context.py shim != f07 implementation")
    ok("turn_context.py shim → features/f07_agent_control")

    class FakeSession:
        phase = "Phase 1"
        player_turn = 1
        place_id = "nvidia_reception"
        stats = {"vision": 0, "execution": 0, "trust": 10, "burnout": 0}

    ctx = build_turn_context(FakeSession())
    if not ctx.get("enabled"):
        raise TestFailure("ABCS should be enabled by default")
    if ctx.get("active_agent_ids") != [1]:
        raise TestFailure(f"Phase 1 active agents wrong: {ctx}")
    ok("F07 build_turn_context Phase 1 → active=[1]")

    prefix = format_constraint_prefix(ctx)
    if "系统约束" not in prefix or "Phase 1" not in prefix:
        raise TestFailure(f"constraint prefix missing: {prefix[:80]}")
    ok("F07 L4 format_constraint_prefix")

    if resolve_active_agent_ids("Phase 3", 16) != [2, 3, 4, 5, 6, 7]:
        raise TestFailure("Turn 16 should append Sam to Phase 3 active list")
    ok("F07 Turn 16 Sam activation")

    p1_tools = allowed_tools_for(4, "Phase 1", 1)
    if p1_tools != {"do_nothing"}:
        raise TestFailure(f"Phase 1 CEO tools should be do_nothing only: {p1_tools}")
    ok("F07 L5 Phase 1 CEO tool whitelist")

    if is_move_allowed(7, "Phase 1", 1):
        raise TestFailure("Sam MOVE should be blocked before Turn 16")
    ok("F07 L5 Sam MOVE blocked Turn 1")

    blocked = filter_tool_calls(
        [_ToolCall(tool_name="send_to_group", args={"group_id": 200, "content": "x"})],
        agent_id=4,
        ctx=ctx,
    )
    if not blocked or blocked[0].tool_name != "do_nothing":
        raise TestFailure("send_to_group should be replaced with do_nothing")
    ok("F07 L5 tool_guard blocks GRP for CEO Phase 1")


def test_f05_routing_payload() -> None:
    section("T2 F05 剧情路由 payload 单元")
    from agent_world.hbm_demo.features.f05_story_routing.routing import (
        build_inject_payload,
        node_a_applies,
    )

    class FakeSession:
        phase = "Phase 1"
        player_turn = 1
        stats = {"vision": 0, "execution": 0, "trust": 10, "burnout": 0}

    events, broadcast, turn_ctx = build_inject_payload(FakeSession(), "你好", task_id="t1")
    if len(events) != 1 or events[0]["effect"]["agent_id"] != 1:
        raise TestFailure(f"Phase 1 Turn 1 inject wrong: {events}")
    if "系统约束" not in events[0]["effect"]["text"]:
        raise TestFailure("Phase 1 inject missing ABCS constraint prefix")
    if not turn_ctx.get("enabled"):
        raise TestFailure("Turn 1 missing turn_context")
    ok("Phase 1 Turn 1 → single inject to Agent 1 + L4 prefix")
    if broadcast is not None:
        raise TestFailure("Turn 1 should not broadcast")

    FakeSession.player_turn = 16
    FakeSession.phase = "Phase 3"
    events, broadcast, _ctx16 = build_inject_payload(FakeSession(), "谈判", task_id="t16")
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


def test_e2e_stack(base: str) -> None:
    section(f"T4 E2E HTTP @ {base}")

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

    player_text = "您好，我来汇报 HBM 显存带宽优化方案，想约 Jensen 进一步沟通。"
    code, turn1, cookie = http_json(
        "POST",
        f"{base}{BASE_PATH}/player-turn",
        body={"player_text": player_text},
        cookie=cookie,
        timeout=120.0,
    )
    if code != 200 or not turn1.get("success"):
        raise TestFailure(f"player-turn failed HTTP {code}: {turn1}")
    tdata = turn1.get("data") or {}
    task_id = tdata.get("task_id")
    if not task_id:
        raise TestFailure(f"player-turn missing task_id: {tdata}")
    ok(f"POST /player-turn → task_id={task_id[:8]}…")

    result, cookie = poll_action_result(base, task_id, cookie)
    if result.get("status") != "completed":
        raise TestFailure(f"Turn 1 not completed: {result}")
    public = result.get("public_messages") or []
    observer = result.get("observer_messages") or []
    grp = result.get("group_messages") or []
    if len(grp) > 0:
        raise TestFailure(f"F07 Phase 1 Turn 1 should have 0 GRP, got {len(grp)}: {grp}")
    ok(
        f"GET /action-result completed — F2F={len(public)} observer={len(observer)} "
        f"GRP={len(grp)} turn→{result.get('player_turn')}"
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


def start_stack() -> Tuple[subprocess.Popen[Any], subprocess.Popen[Any], str]:
    stop = ROOT / "agent_world" / "hbm_demo" / "scripts" / "stop_demo.sh"
    subprocess.run(["bash", str(stop)], check=False, capture_output=True)
    time.sleep(1)

    # Fresh world.db so action-result GRP counts reflect this run only (F07 E2E).
    SIM_DIR.mkdir(parents=True, exist_ok=True)
    for stale in (SIM_DIR / "world.db", SIM_DIR / "env_status.json"):
        if stale.exists():
            stale.unlink()

    env = os.environ.copy()
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
        from agent_world.hbm_demo.env_status import is_runner_ready

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
                return runner, flask, base
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
    print("HBM Demo M0–M5 Acceptance Tests (dev_logs/26)")
    failures: List[str] = []

    for fn in (
        test_static_imports,
        test_m1_shared_shims,
        test_m2_game_service_shims,
        test_m3_runner_shims,
        test_m4_http_shims,
        test_m5_f07_abcs,
        test_f05_routing_payload,
        test_runner_module_entry,
    ):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{fn.__name__}: {exc}")
            print(f"  ✗ {exc}")

    runner = flask = None
    try:
        runner, flask, base = start_stack()
        test_e2e_stack(base)
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
    print("ALL M0–M5 TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

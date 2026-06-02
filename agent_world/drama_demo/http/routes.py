"""Flask Blueprint for drama demo HTTP API."""

from __future__ import annotations

from typing import Any, Dict

from flask import Blueprint, jsonify, request, session

from agent_world.drama_demo import game_service as gs
from agent_world.drama_demo.features.f12_world_sync.handler import get_world_snapshot
from agent_world.drama_demo.features.f13_world_loop_control.handler import (
    get_world_loop_status,
    pause_world_loop,
    resume_world_loop,
)
from agent_world.drama_demo.features.f14_world_delta.handler import get_world_delta
from agent_world.drama_demo.features.f15_prompt_trace.handler import (
    get_prompt_trace,
    get_prompt_trace_by_ref,
    list_prompt_traces,
)
from agent_world.drama_demo.http.health import check_stack_health
from agent_world.drama_demo.http.http_errors import service_error_payload
from agent_world.drama_demo.shared.env_status import is_runner_ready, read_env_status

drama_bp = Blueprint("drama", __name__)


def _json_body() -> Dict[str, Any]:
    return request.get_json(silent=True) or {}


def _bad_request(message: str, status: int = 400):
    return jsonify({"success": False, "error": message}), status


def _check_sim_id(sim_id: str):
    # 放行「当前激活的故事」（前端在大厅选/建并激活某故事后，用其 story_id 作 sim_id 玩）。
    from agent_world.drama_demo.shared.story_config import active_story_id

    if sim_id != active_story_id():
        return _bad_request(
            f"unknown or inactive simulation_id: {sim_id}（请先在大厅激活该故事）", 404
        )
    return None


# ============ 大厅：选已有故事 / 建新故事 / 激活起世界 ============

@drama_bp.route("/lobby/stories", methods=["GET"])
def lobby_stories():
    from agent_world.drama_demo.http.world_manager import WORLD_MANAGER

    return jsonify({"success": True, "data": {"stories": WORLD_MANAGER.list_stories()}})


@drama_bp.route("/lobby/stories", methods=["POST"])
def lobby_create_story():
    from agent_world.drama_demo.http.world_manager import WORLD_MANAGER

    body = _json_body()
    premise = str(body.get("premise") or "").strip()
    if len(premise) < 8:
        return _bad_request("请输入一段大概的剧情（至少 8 个字）")
    # acts 不传 → None：不写死任务数，交给管理 agent(Designer) 按剧情自决（前端默认不传）。
    job_id = WORLD_MANAGER.create_story(
        premise=premise,
        player=str(body.get("player") or "一名卷入其中的外来者"),
        title=body.get("title"),
        acts=int(body["acts"]) if str(body.get("acts") or "").strip() else None,
        with_assets=bool(body.get("with_assets", True)),
    )
    return jsonify({"success": True, "data": {"job_id": job_id}})


@drama_bp.route("/lobby/jobs/<job_id>", methods=["GET"])
def lobby_job_status(job_id: str):
    from agent_world.drama_demo.http.world_manager import WORLD_MANAGER

    job = WORLD_MANAGER.jobs.get(job_id)
    if not job:
        return _bad_request("未知任务", 404)
    return jsonify({"success": True, "data": dict(job)})


@drama_bp.route("/lobby/activate", methods=["POST"])
def lobby_activate():
    from agent_world.drama_demo.http.world_manager import WORLD_MANAGER

    story_id = str(_json_body().get("story_id") or "").strip()
    try:
        ready = WORLD_MANAGER.activate(story_id)
    except ValueError as exc:
        return _bad_request(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return _bad_request(f"起世界失败：{exc}", 500)
    return jsonify({"success": True, "data": {"story_id": story_id, "ready": ready}})


# ============ 故事图片资源（设计期 Artist 落盘的封面/场景背景/角色立绘）============

@drama_bp.route("/stories/<story_id>/assets/<path:subpath>", methods=["GET"])
def story_asset(story_id: str, subpath: str):
    """只读服务某故事的图片资源 config/stories/<story_id>/assets/<subpath>。
    剧情模式前端按 place_id/agent_id 据此加载背景与立绘；缺图返回 404 让前端回退占位。"""
    from flask import send_from_directory
    from werkzeug.exceptions import NotFound

    from agent_world.drama_demo.shared.prompt_paths import story_dir
    from agent_world.drama_demo.shared.story_pack import list_story_ids

    if story_id not in list_story_ids():
        return _bad_request("未知故事", 404)
    base = (story_dir(story_id) / "assets").resolve()
    if not base.is_dir():
        return _bad_request("该故事暂无图片资源", 404)
    # 立绘基础图缺失回退：Artist 有时只出了情绪变体(agent_N_<mood>.png) 没出基础图 agent_N.png，
    # 会导致该角色在「中性/未映射情绪」拍因基础图 404、整张立绘消失（前端连基础回退也落空）。
    # 这里基础图缺失时顶替一张情绪变体（偏好沉稳表情）当基础图，保证立绘始终有图可显。
    if not (base / subpath).is_file():
        import re as _re

        m = _re.fullmatch(r"avatars/agent_(\d+)\.png", subpath)
        if m:
            have = {p.name for p in (base / "avatars").glob(f"agent_{m.group(1)}_*.png")}
            prefer = ("confident", "calm", "neutral", "happy", "anxious", "sad", "angry")
            pick = next(
                (f"agent_{m.group(1)}_{mood}.png" for mood in prefer if f"agent_{m.group(1)}_{mood}.png" in have),
                next(iter(sorted(have)), None),
            )
            if pick:
                return send_from_directory(base, f"avatars/{pick}", max_age=3600)
    try:
        return send_from_directory(base, subpath, max_age=3600)
    except NotFound:
        return _bad_request("资源不存在", 404)


@drama_bp.route("/simulations/<sim_id>/session/start", methods=["POST"])
def session_start(sim_id: str):
    """Initialize Flask session with default stats / place_id."""
    err = _check_sim_id(sim_id)
    if err:
        return err

    from agent_world.drama_demo.features.f11_live_turn_sync.task_state import (
        clear_async_state,
    )

    clear_async_state(gs.get_sim_dir())
    hbm = gs.create_session()
    gs.save_session(session, hbm, sim_id)
    env = read_env_status(gs.get_sim_dir()) or {}

    if is_runner_ready(gs.get_sim_dir()):
        from agent_world.drama_demo.features.f13_world_loop_control import resume_if_paused
        from agent_world.drama_demo.http.ipc_helper import get_ipc_client, push_session_mirror

        push_session_mirror(get_ipc_client(str(gs.get_sim_dir())), hbm)
        refreshed_env = resume_if_paused(sim_dir=gs.get_sim_dir())
        if refreshed_env is not None:
            env = refreshed_env

    # 新手引导 + 属性维度（管理 agent 生成，写在活跃故事 meta）随开局一并下发，
    # 前端开局即可弹引导、渲染数据驱动 HUD（缺失则空，故事未定义就不显示）。
    onboarding = None
    stats_dimensions: list = []
    try:
        from agent_world.drama_demo.shared import story_config

        onboarding = (story_config.active_pack().meta or {}).get("onboarding")
        stats_dimensions = story_config.stats_dimensions()
    except Exception:  # noqa: BLE001
        onboarding, stats_dimensions = None, []

    return jsonify(
        {
            "success": True,
            "data": {
                "task_id": hbm.task_id,
                "start_tick": hbm.start_tick,
                "place_id": hbm.place_id,
                "player_turn": hbm.player_turn,
                "stats": hbm.stats,
                "stats_dimensions": stats_dimensions,
                "onboarding": onboarding,
                "env_status": env,
            },
        }
    )


@drama_bp.route("/simulations/<sim_id>/session/reset", methods=["POST"])
def session_reset(sim_id: str):
    """Reset Agent world (IPC) and Flask session for a full playthrough restart."""
    err = _check_sim_id(sim_id)
    if err:
        return err

    try:
        data = gs.reset_demo(session, sim_id=sim_id)
    except Exception as exc:  # noqa: BLE001
        body, code = service_error_payload(exc)
        return jsonify(body), code

    return jsonify({"success": True, "data": data})


@drama_bp.route("/simulations/<sim_id>/session", methods=["GET"])
def session_get(sim_id: str):
    """Return current game session snapshot (stats / turn)."""
    err = _check_sim_id(sim_id)
    if err:
        return err

    data = gs.get_session_snapshot(session, sim_id)
    return jsonify({"success": True, "data": data})


@drama_bp.route("/simulations/<sim_id>/health", methods=["GET"])
def health_check(sim_id: str):
    """Check Runner + world.db readiness before player-turn."""
    err = _check_sim_id(sim_id)
    if err:
        return err

    data = check_stack_health(gs.get_sim_dir())
    status_code = 200 if data.get("ready") else 503
    return jsonify({"success": data.get("ready", False), "data": data}), status_code


@drama_bp.route("/simulations/<sim_id>/env-status", methods=["GET"])
def env_status(sim_id: str):
    """Read Runner ``env_status.json``."""
    err = _check_sim_id(sim_id)
    if err:
        return err

    env = read_env_status(gs.get_sim_dir())
    if env is None:
        return _bad_request("env_status.json not found; is run_drama started?", 503)

    return jsonify({"success": True, "data": env})


@drama_bp.route("/simulations/<sim_id>/player-turn", methods=["POST"])
def player_turn(sim_id: str):
    """API 1 — score, inject, return task_id for polling."""
    err = _check_sim_id(sim_id)
    if err:
        return err

    body = _json_body()
    player_text = str(body.get("player_text") or "").strip()
    if not player_text:
        return _bad_request("player_text is required")

    try:
        result = gs.handle_player_turn(
            session,
            sim_id=sim_id,
            player_text=player_text,
            request_place_id=body.get("place_id"),
            request_player_turn=body.get("player_turn"),
            tick_count=int(body.get("tick_count", 6)),
        )
    except Exception as exc:  # noqa: BLE001
        body, code = service_error_payload(exc)
        return jsonify(body), code

    return jsonify({"success": True, "data": result})


@drama_bp.route("/simulations/<sim_id>/player-action", methods=["POST"])
def player_action(sim_id: str):
    """玩家主动动作：私信(rdc)/移动(move)/加群(grp)。加群受群聊门控。"""
    err = _check_sim_id(sim_id)
    if err:
        return err

    body = _json_body()
    action = str(body.get("action") or "").strip()
    if not action:
        return _bad_request("action is required (rdc|move|grp)")

    try:
        result = gs.handle_player_action(session, sim_id=sim_id, action=action, body=body)
    except Exception as exc:  # noqa: BLE001
        payload, code = service_error_payload(exc)
        return jsonify(payload), code

    return jsonify({"success": True, "data": result})


@drama_bp.route("/simulations/<sim_id>/joinable-groups", methods=["GET"])
def joinable_groups(sim_id: str):
    """玩家当前可加入的群 id 列表（前端只展示可加群，避免盲填）。"""
    err = _check_sim_id(sim_id)
    if err:
        return err
    try:
        result = gs.get_joinable_groups(session, sim_id=sim_id)
    except Exception as exc:  # noqa: BLE001
        payload, code = service_error_payload(exc)
        return jsonify(payload), code
    return jsonify({"success": True, "data": result})


@drama_bp.route("/simulations/<sim_id>/action-result", methods=["GET"])
def action_result(sim_id: str):
    """API 2 — poll until NPC activity completes or timeout."""
    err = _check_sim_id(sim_id)
    if err:
        return err

    task_id = str(request.args.get("task_id") or "").strip()
    if not task_id:
        return _bad_request("task_id query parameter is required")

    since_tick_raw = request.args.get("since_tick")
    since_tick: int | None = None
    if since_tick_raw is not None and str(since_tick_raw).strip() != "":
        try:
            since_tick = int(since_tick_raw)
        except ValueError:
            return _bad_request("since_tick must be an integer")

    try:
        result = gs.get_action_result(
            session,
            sim_id=sim_id,
            task_id=task_id,
            request_place_id=request.args.get("place_id"),
            since_tick=since_tick,
        )
    except Exception as exc:  # noqa: BLE001
        body, code = service_error_payload(exc)
        return jsonify(body), code

    return jsonify({"success": True, "data": result})


@drama_bp.route("/simulations/<sim_id>/world-snapshot", methods=["GET"])
def world_snapshot(sim_id: str):
    """F12 — full world read-model snapshot for UI calibration."""
    err = _check_sim_id(sim_id)
    if err:
        return err

    try:
        data = get_world_snapshot(session, sim_id=sim_id)
    except Exception as exc:  # noqa: BLE001
        body, code = service_error_payload(exc)
        return jsonify(body), code

    return jsonify({"success": True, "data": data})


@drama_bp.route("/simulations/<sim_id>/world-delta", methods=["GET"])
def world_delta(sim_id: str):
    """F14 — session-scoped incremental world sync (since_tick poll)."""
    err = _check_sim_id(sim_id)
    if err:
        return err

    since_tick_raw = request.args.get("since_tick")
    since_tick: int | None = None
    if since_tick_raw is not None and str(since_tick_raw).strip() != "":
        try:
            since_tick = int(since_tick_raw)
        except ValueError:
            return _bad_request("since_tick must be an integer")

    try:
        data = get_world_delta(
            session,
            sim_id=sim_id,
            since_tick=since_tick,
        )
    except Exception as exc:  # noqa: BLE001
        body, code = service_error_payload(exc)
        return jsonify(body), code

    return jsonify({"success": True, "data": data})


@drama_bp.route("/simulations/<sim_id>/world-loop/status", methods=["GET"])
def world_loop_status(sim_id: str):
    """F13 — resident world loop status."""
    err = _check_sim_id(sim_id)
    if err:
        return err
    try:
        data = get_world_loop_status(sim_dir=gs.get_sim_dir())
    except Exception as exc:  # noqa: BLE001
        body, code = service_error_payload(exc)
        return jsonify(body), code
    return jsonify({"success": True, "data": data})


@drama_bp.route("/simulations/<sim_id>/world-loop/pause", methods=["POST"])
def world_loop_pause(sim_id: str):
    """F13 — pause resident world tick loop."""
    err = _check_sim_id(sim_id)
    if err:
        return err
    try:
        data = pause_world_loop(sim_dir=gs.get_sim_dir())
    except Exception as exc:  # noqa: BLE001
        body, code = service_error_payload(exc)
        return jsonify(body), code
    return jsonify({"success": True, "data": data})


@drama_bp.route("/simulations/<sim_id>/world-loop/resume", methods=["POST"])
def world_loop_resume(sim_id: str):
    """F13 — resume resident world tick loop."""
    err = _check_sim_id(sim_id)
    if err:
        return err
    try:
        data = resume_world_loop(sim_dir=gs.get_sim_dir())
    except Exception as exc:  # noqa: BLE001
        body, code = service_error_payload(exc)
        return jsonify(body), code
    return jsonify({"success": True, "data": data})


@drama_bp.route("/simulations/<sim_id>/prompt-trace/<trace_id>", methods=["GET"])
def prompt_trace_get(sim_id: str, trace_id: str):
    """F15 — fetch full LLM trace by id."""
    err = _check_sim_id(sim_id)
    if err:
        return err
    try:
        data = get_prompt_trace(sim_dir=gs.get_sim_dir(), trace_id=str(trace_id))
    except KeyError:
        return _bad_request(f"trace not found: {trace_id}", 404)
    except Exception as exc:  # noqa: BLE001
        body, code = service_error_payload(exc)
        return jsonify(body), code
    return jsonify({"success": True, "data": data})


@drama_bp.route("/simulations/<sim_id>/prompt-trace/by-ref", methods=["GET"])
def prompt_trace_by_ref(sim_id: str):
    """F15 — UI path: resolve trace from ref_key."""
    err = _check_sim_id(sim_id)
    if err:
        return err
    ref_key = str(request.args.get("ref_key") or "").strip()
    if not ref_key:
        return _bad_request("ref_key query parameter is required")
    try:
        data = get_prompt_trace_by_ref(sim_dir=gs.get_sim_dir(), ref_key=ref_key)
    except KeyError:
        return _bad_request(f"no trace for ref_key: {ref_key}", 404)
    except Exception as exc:  # noqa: BLE001
        body, code = service_error_payload(exc)
        return jsonify(body), code
    return jsonify({"success": True, "data": data})


@drama_bp.route("/simulations/<sim_id>/prompt-traces", methods=["GET"])
def prompt_traces_list(sim_id: str):
    """F15 — optional batch listing for scripts/curl."""
    err = _check_sim_id(sim_id)
    if err:
        return err
    agent_id_raw = request.args.get("agent_id")
    since_tick_raw = request.args.get("since_tick")
    limit_raw = request.args.get("limit", "50")
    agent_id: int | None = None
    since_tick: int | None = None
    if agent_id_raw is not None and str(agent_id_raw).strip():
        try:
            agent_id = int(agent_id_raw)
        except ValueError:
            return _bad_request("agent_id must be an integer")
    if since_tick_raw is not None and str(since_tick_raw).strip():
        try:
            since_tick = int(since_tick_raw)
        except ValueError:
            return _bad_request("since_tick must be an integer")
    try:
        limit = int(limit_raw)
    except ValueError:
        return _bad_request("limit must be an integer")
    try:
        data = list_prompt_traces(
            sim_dir=gs.get_sim_dir(),
            agent_id=agent_id,
            since_tick=since_tick,
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        body, code = service_error_payload(exc)
        return jsonify(body), code
    return jsonify({"success": True, "data": data})


@drama_bp.route("/simulations/<sim_id>/debug-inject", methods=["POST"])
def debug_inject(sim_id: str):
    """Phase 2 temporary endpoint — kept for manual IPC testing."""
    err = _check_sim_id(sim_id)
    if err:
        return err

    body = _json_body()
    player_text = str(body.get("player_text") or "").strip()
    if not player_text:
        return _bad_request("player_text is required")

    tick_count = int(body.get("tick_count", 6))
    hbm = gs.get_or_create_session(session, sim_id)

    try:
        inject_result = gs.run_debug_inject(
            hbm,
            player_text,
            tick_count=tick_count,
        )
    except Exception as exc:  # noqa: BLE001
        body, code = service_error_payload(exc)
        return jsonify(body), code

    gs.save_session(session, hbm, sim_id)
    env = read_env_status(gs.get_sim_dir()) or {}

    return jsonify(
        {
            "success": True,
            "data": {
                "task_id": hbm.task_id,
                "player_turn": hbm.player_turn,
                "inject": inject_result,
                "env_status": env,
            },
        }
    )

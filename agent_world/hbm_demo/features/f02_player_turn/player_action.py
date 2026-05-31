"""玩家主动动作受理（需求二/三）：私信 RDC / 移动 MOVE / 加群 GRP。

与 F2F 主回合（handler.py）平级的轻量入口——不打分、不构 inject，只把动作落到 IPC：
  - rdc/grp 经 player_input_queue（world_loop drain 时 apply）
  - move 复用现成 send_move_agent IPC（引擎正经移动）+ 同步 session.place_id
GRP 在受理时先过群聊门控 can_player_join_group（需求三）；门控默认开，HBM_GROUP_GATE=0 可关。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f01_session.lifecycle import save_session
from agent_world.hbm_demo.features.f01_session.paths import get_sim_dir
from agent_world.hbm_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.hbm_demo.features.f07_agent_control.group_gate import (
    can_player_join_group,
    joinable_groups_for_player,
)
from agent_world.hbm_demo.features.f17_virtual_player.config import is_f08_enabled, player_agent_id
from agent_world.hbm_demo.features.f17_virtual_player.player_actions import (
    build_player_grp_payload,
    build_player_rdc_payload,
)
from agent_world.hbm_demo.http.ipc_helper import (
    get_ipc_client,
    send_enqueue_player_input,
    send_move_agent,
)
from agent_world.hbm_demo.shared.env_status import read_env_status

log = logging.getLogger("agent_world.hbm_demo.f02.player_action")


def _group_gate_enabled() -> bool:
    return os.environ.get("HBM_GROUP_GATE", "1").strip().lower() not in ("0", "false", "no", "off")


def _current_tick(sim_dir: Any) -> int:
    env = read_env_status(sim_dir) or {}
    try:
        return int(env.get("tick") or env.get("current_tick") or 0)
    except (TypeError, ValueError):
        return 0


def handle_player_action(session: Any, *, sim_id: str, action: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """受理一个玩家动作，返回 {accepted, ...}。action ∈ {rdc, move, grp}。"""
    if not is_f08_enabled():
        return {"accepted": False, "reason": "virtual_player_disabled"}
    sim = get_sim_dir(sim_id)
    ipc_client = get_ipc_client(str(sim))
    act = str(action or "").strip().lower()

    if act == "rdc":
        target = body.get("target_id")
        payload = build_player_rdc_payload(session, target, str(body.get("content") or ""))
        if not payload:
            return {"accepted": False, "reason": "invalid_rdc"}
        send_enqueue_player_input(ipc_client, events=[], player_rdc=payload)
        return {"accepted": True, "action": "rdc", "recipient_id": payload["recipient_id"]}

    if act == "move":
        place_id = str(body.get("place_id") or "").strip()
        if not place_id:
            return {"accepted": False, "reason": "invalid_move"}
        resp = send_move_agent(ipc_client, agent_id=int(player_agent_id()), place_id=place_id)
        # 引擎把非法地点/容量满吞成 status=completed + result.error；不能盲目同步 session 位置。
        move_err = (getattr(resp, "result", None) or {}).get("error")
        if move_err:
            log.warning("player move → %s rejected: %s", place_id, move_err)
            return {"accepted": False, "reason": "move_failed", "detail": str(move_err)}
        session.place_id = place_id  # 仅在引擎确认移动后同步（后续 F2F/inject 用新地点）
        save_session_safe(session, sim_id)
        log.info("player move → %s", place_id)
        return {"accepted": True, "action": "move", "place_id": place_id}

    if act == "grp":
        group_id = body.get("group_id")
        if group_id is None:
            return {"accepted": False, "reason": "invalid_grp"}
        if _group_gate_enabled():
            db = make_readonly_db(sim)
            ok = can_player_join_group(
                db,
                int(group_id),
                player_place=str(getattr(session, "place_id", "nvidia_reception")),
                since_t=int(getattr(session, "start_tick", 0) or 0),
                t_now=_current_tick(sim) or 10**9,
            )
            if not ok:
                return {"accepted": False, "reason": "not_consented",
                        "hint": "需先 F2F 见过群里某成员并得到其同意"}
        payload = build_player_grp_payload(session, int(group_id), str(body.get("content") or ""))
        if not payload:
            return {"accepted": False, "reason": "invalid_grp"}
        send_enqueue_player_input(ipc_client, events=[], player_grp=payload)
        return {"accepted": True, "action": "grp", "group_id": int(group_id)}

    return {"accepted": False, "reason": f"unknown_action:{act}"}


def get_joinable_groups(session: Any, *, sim_id: str) -> Dict[str, Any]:
    """玩家当前可加入的群 id 列表（已 F2F 见过某成员且其同意）。供前端只显示可加群（P5）。"""
    if not is_f08_enabled() or not _group_gate_enabled():
        # 门控关时所有群都可加；但不查全部群避免越权，返回空让前端走自由输入兜底。
        return {"groups": [], "gate_enabled": _group_gate_enabled()}
    sim = get_sim_dir(sim_id)
    db = make_readonly_db(sim)
    gids = joinable_groups_for_player(
        db,
        player_place=str(getattr(session, "place_id", "nvidia_reception")),
        since_t=int(getattr(session, "start_tick", 0) or 0),
        t_now=_current_tick(sim) or 10**9,
    )
    return {"groups": [{"group_id": int(g)} for g in gids], "gate_enabled": True}


def save_session_safe(session: Any, sim_id: str) -> None:
    from flask import session as flask_session

    try:
        save_session(flask_session, session, sim_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("save_session after move failed: %s", exc)


__all__ = ["handle_player_action", "get_joinable_groups"]

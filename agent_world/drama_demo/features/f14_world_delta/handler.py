"""F14 GET /world-delta — session-scoped incremental sync (dev_logs/31 §十四)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from agent_world.drama_demo.features.f01_session.lifecycle import load_session
from agent_world.drama_demo.features.f01_session.paths import get_name_map, get_sim_dir
from agent_world.drama_demo.features.f04_stats.deltas import initial_stats
from agent_world.drama_demo.features.f05_story_routing.watcher import (
    consume_game_over_payload,
    consume_routing_world_events,
    scan_routing_if_needed,
)
from agent_world.drama_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.drama_demo.features.f12_world_sync.delta import build_session_world_delta
from agent_world.drama_demo.shared.env_status import read_env_status
from agent_world.drama_demo.shared.errors import RunnerNotReadyError


def get_world_delta(
    flask_session: Any,
    *,
    sim_id: str,
    since_tick: Optional[int] = None,
    sim_dir: Path | None = None,
) -> Dict[str, Any]:
    """Return incremental world delta for the current Flask session."""
    sim = sim_dir or get_sim_dir()
    env = read_env_status(sim)
    if env is None:
        raise RunnerNotReadyError(
            "Runner not ready: start run_drama first and wait for env_status.json"
        )

    hbm = load_session(flask_session, sim_id)
    t_now = int(env.get("current_tick", 0))
    client_since = max(0, int(since_tick)) if since_tick is not None else 0

    if hbm is not None:
        scan_routing_if_needed(
            flask_session,
            hbm,
            sim_id=sim_id,
            sim_dir=sim,
            current_tick=t_now,
        )

    from agent_world.drama_demo.shared import story_config

    db = make_readonly_db(sim)
    name_map = get_name_map()
    # 玩家位置以**引擎世界 DB** 为准：move 经 IPC 即时改的就是它，比 cookie 的 hbm.place_id 更及时，且不会被
    # routing 那条「旧 hbm 快照」回写弹回（即便本次轮询请求是在移动前发起、cookie 还是旧的，DB 也已是新位置）。
    # DB 里查不到玩家(agent 0)时回退 cookie / 起始地点。
    player_place = hbm.place_id if hbm else story_config.player_start_place()
    try:
        _ploc = (db.fetch_all_agent_locations() or {}).get(0) or {}
        if _ploc.get("place_id"):
            player_place = str(_ploc["place_id"])
    except Exception:  # noqa: BLE001
        pass
    routing_events = consume_routing_world_events(
        flask_session,
        since_tick=client_since,
        t_now=t_now,
    )

    delta = build_session_world_delta(
        since_tick=client_since,
        t_now=t_now,
        player_place_id=player_place,
        db=db,
        name_map=name_map,
        extra_world_events=routing_events,
    )

    # 当前「线索」：此刻已上膛、未触发的非结局 bert 的玩家向 hint。随玩家触发 bert 自动推进 → 前端那行线索逐条更新。
    clues: list = []
    if hbm is not None:
        try:
            clues = story_config.current_clues(getattr(hbm, "fired_berts", None) or [])
        except Exception:  # noqa: BLE001
            clues = []

    result: Dict[str, Any] = {
        **delta,
        "current_tick": t_now,
        "loop_state": env.get("loop_state"),
        "stats_update": dict(hbm.stats) if hbm else initial_stats(),
        "player_turn": hbm.player_turn if hbm else 1,
        # 让 delta 自洽：带上 name_map(agent_id→名)，前端轮询不必依赖 snapshot 缓存、也无需写死角色名。
        "name_map": {str(k): v for k, v in name_map.items()},
        "clues": clues,
        # 故事定义的全部地点——前端据此列出所有可去地点（含没人的空房间），玩家可自由探索。
        "places": story_config.active_place_ids(),
    }

    game_over = consume_game_over_payload(flask_session)
    if game_over:
        result["game_over"] = game_over
    elif hbm and hbm.ending_id:
        # 结局由命中的「结局 bert」决定：收场文案/基调已在触发时写入 hbm（good/neutral/bad）；
        # story_graph 退役，无 graph.endings 回退，kind 缺省兜底 neutral。
        end_kind = hbm.ending_kind or "neutral"
        end_summary = hbm.ending_summary or ""
        result["game_over"] = {
            "status": "game_over" if end_kind == "bad" else "completed",
            "ending_id": hbm.ending_id,
            "ending_summary": end_summary,
            "ending_kind": end_kind,
            "stats_update": dict(hbm.stats),
        }

    return result


__all__ = ["get_world_delta"]

"""F01 Flask session lifecycle."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from agent_world.drama_demo.features.f01_session.constants import (
    DEFAULT_PLACE_ID,
    DEFAULT_SIM_ID,
    SESSION_KEY,
)
from agent_world.drama_demo.features.f01_session.models import DramaSession
from agent_world.drama_demo.features.f01_session.paths import get_sim_dir
from agent_world.drama_demo.shared.env_status import is_runner_ready, read_env_status


def create_session(sim_dir: Path | None = None) -> DramaSession:
    sim = sim_dir or get_sim_dir()
    env = read_env_status(sim) or {}
    start_tick = int(env.get("current_tick", 0))
    # 剧情改由 bert（条件→反应）驱动，已无「初始节点/幕」：只从活跃 Story Pack 取玩家起始地点与初始属性。
    from agent_world.drama_demo.shared import story_config

    try:
        place_id = story_config.player_start_place()
    except Exception:  # noqa: BLE001 — 无 Story Pack 时回退默认
        place_id = DEFAULT_PLACE_ID
    try:
        stats = story_config.initial_stats()
    except Exception:  # noqa: BLE001 — 无 Story Pack 时空属性
        stats = {}
    return DramaSession(
        task_id=f"task_{uuid.uuid4().hex[:12]}",
        start_tick=start_tick,
        place_id=place_id,
        player_turn=1,
        stats=stats,
    )


def save_session(flask_session: Any, hbm: DramaSession, sim_id: str = DEFAULT_SIM_ID) -> None:
    store = flask_session.setdefault(SESSION_KEY, {})
    store[sim_id] = hbm.to_dict()
    flask_session.modified = True


def load_session(
    flask_session: Any,
    sim_id: str = DEFAULT_SIM_ID,
) -> Optional[DramaSession]:
    store = flask_session.get(SESSION_KEY) or {}
    raw = store.get(sim_id)
    if not raw:
        return None
    return DramaSession.from_dict(raw)


def get_or_create_session(
    flask_session: Any,
    sim_id: str = DEFAULT_SIM_ID,
    *,
    sim_dir: Path | None = None,
) -> DramaSession:
    existing = load_session(flask_session, sim_id)
    if existing is not None:
        return existing
    hbm = create_session(sim_dir)
    save_session(flask_session, hbm, sim_id)
    return hbm


def get_session_snapshot(
    flask_session: Any,
    sim_id: str = DEFAULT_SIM_ID,
    *,
    sim_dir: Path | None = None,
) -> Dict[str, Any]:
    sim = sim_dir or get_sim_dir()
    from agent_world.drama_demo.features.f11_live_turn_sync.task_state import sync_runtime_state

    sync_runtime_state(flask_session, sim_id, sim_dir=sim)
    env = read_env_status(sim) or {}
    runner_ready = is_runner_ready(sim)
    hbm = load_session(flask_session, sim_id)
    if hbm is None:
        return {
            "initialized": False,
            "sim_id": sim_id,
            "runner_ready": runner_ready,
            "env_status": env,
        }
    # 新手引导 + 属性维度（管理 agent 设计期生成，写在活跃故事的 meta；缺失则空）+ 开局当前线索。
    onboarding = None
    stats_dimensions: list = []
    clues: list = []
    places: list = []
    try:
        from agent_world.drama_demo.shared import story_config

        pack = story_config.active_pack()
        onboarding = (pack.meta or {}).get("onboarding")
        stats_dimensions = story_config.stats_dimensions()
        clues = pack.berts.current_hints(set(getattr(hbm, "fired_berts", None) or []))
        places = story_config.active_place_ids()
    except Exception:  # noqa: BLE001
        onboarding, stats_dimensions, clues, places = None, [], [], []
    return {
        "initialized": True,
        "sim_id": sim_id,
        "task_id": hbm.task_id,
        "start_tick": hbm.start_tick,
        "place_id": hbm.place_id,
        "onboarding": onboarding,
        "stats_dimensions": stats_dimensions,
        "clues": clues,
        # 故事定义的**全部**地点（不只玩家/NPC 当前所在地）——前端据此列出所有可去的地方，
        # 空房间（如档案室/挂号大厅）也能走过去探索，不再只显示有人的那一个。
        "places": places,
        "player_turn": hbm.player_turn,
        "stats": dict(hbm.stats),
        "stats_update": dict(hbm.stats),
        "runner_ready": runner_ready,
        "env_status": env,
    }

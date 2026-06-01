"""F01 Flask session lifecycle."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f01_session.constants import (
    DEFAULT_PHASE,
    DEFAULT_PLACE_ID,
    DEFAULT_SIM_ID,
    SESSION_KEY,
)
from agent_world.hbm_demo.features.f01_session.models import HbmSession
from agent_world.hbm_demo.features.f01_session.paths import get_sim_dir
from agent_world.hbm_demo.shared.env_status import is_runner_ready, read_env_status


def create_session(sim_dir: Path | None = None) -> HbmSession:
    sim = sim_dir or get_sim_dir()
    env = read_env_status(sim) or {}
    start_tick = int(env.get("current_tick", 0))
    # 节点驱动：从活跃 Story Pack 取初始节点/地点（替代写死的 HBM Phase 1 / nvidia_reception）。
    from agent_world.hbm_demo.shared import story_config

    try:
        init_node = story_config.initial_node_id()
        place_id = story_config.player_start_place()
        phase = story_config.node_beats_label(init_node) or DEFAULT_PHASE
    except Exception:  # noqa: BLE001 — 无 Story Pack 时回退默认
        init_node, place_id, phase = None, DEFAULT_PLACE_ID, DEFAULT_PHASE
    try:
        stats = story_config.initial_stats()
    except Exception:  # noqa: BLE001 — 无 Story Pack 时空属性
        stats = {}
    return HbmSession(
        task_id=f"task_{uuid.uuid4().hex[:12]}",
        start_tick=start_tick,
        place_id=place_id,
        phase=phase,
        current_node_id=init_node,
        node_entered_tick=start_tick,
        player_turn=1,
        stats=stats,
    )


def save_session(flask_session: Any, hbm: HbmSession, sim_id: str = DEFAULT_SIM_ID) -> None:
    store = flask_session.setdefault(SESSION_KEY, {})
    store[sim_id] = hbm.to_dict()
    flask_session.modified = True


def load_session(
    flask_session: Any,
    sim_id: str = DEFAULT_SIM_ID,
) -> Optional[HbmSession]:
    store = flask_session.get(SESSION_KEY) or {}
    raw = store.get(sim_id)
    if not raw:
        return None
    return HbmSession.from_dict(raw)


def get_or_create_session(
    flask_session: Any,
    sim_id: str = DEFAULT_SIM_ID,
    *,
    sim_dir: Path | None = None,
) -> HbmSession:
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
    from agent_world.hbm_demo.features.f11_live_turn_sync.task_state import sync_runtime_state

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
    # 新手引导 + 属性维度（管理 agent 设计期生成，写在活跃故事的 meta；缺失则空）。
    onboarding = None
    stats_dimensions: list = []
    try:
        from agent_world.hbm_demo.shared import story_config

        onboarding = (story_config.active_pack().meta or {}).get("onboarding")
        stats_dimensions = story_config.stats_dimensions()
    except Exception:  # noqa: BLE001
        onboarding, stats_dimensions = None, []
    return {
        "initialized": True,
        "sim_id": sim_id,
        "task_id": hbm.task_id,
        "start_tick": hbm.start_tick,
        "place_id": hbm.place_id,
        "phase": hbm.phase,
        "current_phase": hbm.phase,
        "tension": hbm.tension,
        "onboarding": onboarding,
        "stats_dimensions": stats_dimensions,
        "player_turn": hbm.player_turn,
        "stats": dict(hbm.stats),
        "stats_update": dict(hbm.stats),
        "runner_ready": runner_ready,
        "env_status": env,
    }

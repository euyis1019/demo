"""F01 sim paths and cached scenario/name lookups."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from agent_world.hbm_demo.features.f01_session.constants import DEFAULT_CONFIG, DEFAULT_SIM_ID
from agent_world.hbm_demo.shared.config_loader import load_scenario

_scenario_cache: Dict[str, Any] | None = None
_name_map_cache: Dict[int, str] | None = None


def get_sim_dir() -> Path:
    # 当前在玩哪个故事 → 哪个 sim 目录（前端选/建故事后可运行期切换）。
    from agent_world.hbm_demo.shared.active_game import active_sim_dir

    return active_sim_dir()


def clear_scenario_cache() -> None:
    """切换故事时清掉按故事缓存的 scenario / name_map（否则会沿用上一个故事）。"""
    global _scenario_cache, _name_map_cache
    _scenario_cache = None
    _name_map_cache = None


def get_world_db_path(sim_dir: Path | None = None) -> Path:
    return (sim_dir or get_sim_dir()) / "world.db"


def get_scenario() -> Dict[str, Any]:
    global _scenario_cache
    if _scenario_cache is None:
        # 数据驱动：默认从活跃 Story Pack 投影出 scenario（与 Runner 播种同源），
        # 仅当显式关闭播种时才回退外部 hbm_scenario.yaml。
        from agent_world.hbm_demo.shared.story_pack.scenario_adapter import (
            is_story_pack_seed_enabled,
            story_pack_to_scenario,
        )

        if is_story_pack_seed_enabled():
            from agent_world.hbm_demo.shared import story_config

            _scenario_cache = story_pack_to_scenario(story_config.active_pack())
        else:
            _scenario_cache = load_scenario(DEFAULT_CONFIG)
    return _scenario_cache


def get_name_map() -> Dict[int, str]:
    global _name_map_cache
    if _name_map_cache is None:
        _name_map_cache = {
            int(a["agent_id"]): str(a.get("name") or f"agent_{a['agent_id']}")
            for a in get_scenario().get("agents", [])
        }
    return _name_map_cache

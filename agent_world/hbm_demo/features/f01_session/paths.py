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
    pkg = Path(__file__).resolve().parents[2]
    default = pkg / "sim" / DEFAULT_SIM_ID
    raw = Path(os.environ.get("HBM_SIM_DIR", str(default)))
    return raw.resolve()


def get_world_db_path(sim_dir: Path | None = None) -> Path:
    return (sim_dir or get_sim_dir()) / "world.db"


def get_scenario() -> Dict[str, Any]:
    global _scenario_cache
    if _scenario_cache is None:
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

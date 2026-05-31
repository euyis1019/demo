"""F01 session constants and default game state."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

_HBM_DEMO_ROOT = Path(__file__).resolve().parents[2]

# 活跃故事 = 当前在玩哪个 Story Pack（env HBM_STORY_ID 切换；默认 hbm_memory_war）。
# 它同时是 HTTP sim_id（routes 放行）、watcher 解释器加载的故事、Runner 播种的故事。
DEFAULT_SIM_ID = (os.environ.get("HBM_STORY_ID") or "canglan_sword").strip() or "canglan_sword"
DEFAULT_PLACE_ID = "nvidia_reception"
DEFAULT_PHASE = "Phase 1"
DEFAULT_CONFIG = _HBM_DEMO_ROOT / "hbm_scenario.yaml"

INITIAL_STATS: Dict[str, int] = {
    "vision": 0,
    "execution": 0,
    "trust": 10,
    "burnout": 0,
}

SESSION_KEY = "hbm_game"
TASKS_KEY = "hbm_tasks"

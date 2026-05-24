"""F01 session constants and default game state."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

_HBM_DEMO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_SIM_ID = "hbm_memory_war"
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

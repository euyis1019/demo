"""F01 session constants and default game state."""

from __future__ import annotations

import os
from typing import Dict

# 活跃故事 = 当前在玩哪个 Story Pack（默认 canglan_sword；env DRAMA_STORY_ID 设初值，
# 运行期由 active_game/WorldManager 在大厅选/建故事后切换）。
# 它同时是 HTTP sim_id（routes 放行）、watcher 解释器加载的故事、Runner 播种的故事。
DEFAULT_SIM_ID = (os.environ.get("DRAMA_STORY_ID") or "canglan_sword").strip() or "canglan_sword"
# 中性兜底——真实值数据驱动：地点/幕名来自活跃 Story Pack 的初始节点，属性维度来自 meta.stats。
DEFAULT_PLACE_ID = ""
DEFAULT_PHASE = ""

# 属性面板维度数据驱动：初始值来自 meta.stats（见 story_config.initial_stats），这里不再写死任何故事维度。
INITIAL_STATS: Dict[str, int] = {}

SESSION_KEY = "drama_game"
TASKS_KEY = "drama_tasks"

"""Story id 命名：把玩家输入的一段剧情概要 slug 成一个 ASCII story_id。

单一来源：WorldManager（大厅新建）与 scripts/ops/new_game.py（命令行新建）共用，
避免两处各写一套 ASCII 化规则后发散。
"""

from __future__ import annotations

import re
import time


def slug_story_id(premise: str) -> str:
    # 只取 ASCII（story_id 进 URL 路径，非 ASCII 会让 http 请求失败）；中文 premise → "story_<ts>"
    ascii_part = re.sub(r"[^0-9a-zA-Z]+", "_", (premise or "").strip()).strip("_")[:16]
    return f"{ascii_part or 'story'}_{int(time.time()) % 100000}"

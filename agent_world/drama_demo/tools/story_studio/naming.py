"""Story id 命名：把玩家输入的标题/剧情概要 slug 成一个有意义的 ASCII story_id。

单一来源：WorldManager（大厅新建）与 scripts/ops/new_game.py（命令行新建）共用，
避免两处各写一套 ASCII 化规则后发散。

中文 → 拼音（可读 ASCII，如「静屿灯塔谋杀案」→ jing_yu_deng_ta_mou_sha_an_<ts>），
优先用标题（更短更贴切）；无 pypinyin 时回退纯 ASCII 提取（中文则退化为 story_<ts>）。
"""

from __future__ import annotations

import re
import time


def slug_story_id(premise: str, title: str = "") -> str:
    # 优先标题（短、贴切），否则用 premise 开头；story_id 进 URL 路径，必须 ASCII。
    src = (title or premise or "").strip()[:24]
    ascii_part = ""
    try:  # 中文转拼音得到可读 ASCII；ASCII 词原样保留
        from pypinyin import lazy_pinyin

        toks = lazy_pinyin(src)
        ascii_part = re.sub(r"[^0-9a-zA-Z]+", "_", "_".join(toks)).strip("_")[:28]
    except Exception:  # noqa: BLE001 — 缺 pypinyin/转换失败则回退
        pass
    if not ascii_part:  # 回退：直接抽 ASCII（纯中文则为空 → story）
        ascii_part = re.sub(r"[^0-9a-zA-Z]+", "_", src).strip("_")[:16]
    return f"{(ascii_part or 'story').lower()}_{int(time.time()) % 100000}"

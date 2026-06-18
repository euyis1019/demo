"""羁绊（好友/心结）—— 由好感分**自动派生**（焐心小镇·B4，系统派生版）。

背景：实测 deepseek-v4-flash 基本不会自主调用 relation_change 这类「结构/元」工具
（好感拉满也不结好友），挂着只是死重 + 稀释核心社交工具。故改为**从好感分派生**：
好感攒到很高＝自然成了「好友」，跌到很低＝结下「心结」。这与现成的 5 档等级一样
是对【LLM 自主给出的好感分】的纯展示派生，不新增规则、不指挥 NPC 行为、不写库。

私聊可达性始终由 neighbor 关系提供，本派生只读好感、绝不动关系图 → 私聊永不被锁
（与「不锁私聊」决策一致）。羁绊渲进第 6 段影响语气、随快照下发前端显示/弹里程碑。
"""

from __future__ import annotations

from typing import Optional

BOND_TYPES = ("好友", "心结")

FRIEND_AT = 75   # 好感 ≥ 此值＝「好友」（介于 亲密60 与 挚友80 之间的郑重里程碑）
RIFT_AT = 8      # 好感 ≤ 此值＝「心结」（种子起步 10-45，跌破即明显交恶）


def bond_from_score(score: Optional[int]) -> Optional[str]:
    """好感分 → 羁绊（'好友'/'心结'/None）。"""
    if score is None:
        return None
    if score >= FRIEND_AT:
        return "好友"
    if score <= RIFT_AT:
        return "心结"
    return None

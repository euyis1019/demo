"""引擎 5 段系统提示词标题（原 config.SEGMENT_HEADERS，W6 集中至 prompts）。

经 runtime/world_factory 注入引擎 PerceptionBuilder(segment_headers=...)，
成为每个 NPC system prompt 的段落骨架。

⚠ 段数与顺序必须与引擎 PerceptionBuilder 的 5 段语义对齐：
  人格内核(soul) / 长期目标 / 当前状态 / 当前小目标 / 场景行为规则——不可重排。
第 6 段（好感度）标题见 prompts/affinity.py；第 7 段（世界事件）见 prompts/directors.py。
"""

from __future__ import annotations

SEGMENT_HEADERS = (
    "# 人格内核",
    "# 长期目标",
    "# 当前状态",
    "# 当前小目标",
    "# 场景行为规则",
)

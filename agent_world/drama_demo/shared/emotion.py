"""情绪离散枚举 + 归一化（前端按情绪切立绘）。

受控情绪枚举供：前端立绘命名变体图（agent_{id}_{emotion}.png）、出图清单(asset_manifest)、
以及 f05 情绪判断 agent(emotion_judge) 校验 LLM 输出。情绪标签本身由**运行期情绪判断 agent**
（features/f05_story_routing/emotion_judge，LLM 读台词判定）产生——旧的关键词兜底分类已删除。
纯枚举/归一，无业务、不依赖 features（D3）。
"""

from __future__ import annotations

from typing import Tuple

# 受控情绪枚举（前端立绘按此命名变体图：agent_{id}_{emotion}.png）。
EMOTIONS: Tuple[str, ...] = ("neutral", "happy", "angry", "sad", "anxious", "confident")
DEFAULT_EMOTION = "neutral"


def normalize_emotion(raw: object) -> str:
    """把任意输入归一到受控枚举；非法/空 → neutral。供情绪 agent 校验 LLM 输出。"""
    text = str(raw or "").strip().lower()
    return text if text in EMOTIONS else DEFAULT_EMOTION

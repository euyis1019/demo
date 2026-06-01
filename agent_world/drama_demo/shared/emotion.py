"""情绪离散标签 + 文本兜底分类（需求一：前端按情绪切立绘）。

把 agent 的自由文本情绪（current_state / 台词）归一成**受控枚举标签**，供 world-delta 下发、
前端据此切换不同立绘。优先让 LLM 在 update_state 直接产出 `emotion` 标签；LLM 没给时用本模块
按关键词兜底分类。纯函数、无业务、不依赖 features（D3）。
"""

from __future__ import annotations

from typing import Dict, Tuple

# 受控情绪枚举（前端立绘按此命名变体图：agent_{id}_{emotion}.png）。
EMOTIONS: Tuple[str, ...] = ("neutral", "happy", "angry", "sad", "anxious", "confident")
DEFAULT_EMOTION = "neutral"

# 关键词表（按优先级排序：强/负面情绪在前，避免「又气又笑」误判成 happy）。
_KEYWORDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("angry", ("愤怒", "生气", "恼火", "发火", "火大", "震怒", "气炸", "拍桌", "怒", "气愤", "恼", "暴怒",
               "气死", "气到", "气得", "动怒", "光火", "怒火", "岂有此理", "放肆", "混账", "可恶", "荒唐",
               "休想", "欺人太甚", "滚", "胡闹", "放屁")),
    ("anxious", ("焦虑", "紧张", "不安", "担心", "慌", "忐忑", "着急", "焦急", "惶恐", "压力", "烦躁", "心急",
                 "怎么办", "糟了", "不妙", "麻烦了", "来不及", "万一", "坐立不安", "心慌")),
    ("sad", ("难过", "伤心", "沮丧", "失落", "悲", "失望", "心灰", "无奈", "黯然", "委屈", "可惜", "遗憾",
             "唉", "心累", "绝望", "心痛")),
    ("happy", ("高兴", "开心", "欣喜", "兴奋", "满意", "喜悦", "欣慰", "畅快", "乐", "笑", "喜", "太好了",
               "棒", "妙", "痛快", "好极了", "惊喜", "乐意")),
    ("confident", ("自信", "胸有成竹", "笃定", "稳操胜券", "得意", "淡定", "从容", "胜券", "镇定", "气定神闲",
                   "放心", "没问题", "交给我", "包在我", "稳了", "搞定", "势在必得", "十拿九稳")),
)


def normalize_emotion(raw: object) -> str:
    """把任意输入归一到受控枚举；非法/空 → neutral。"""
    text = str(raw or "").strip().lower()
    return text if text in EMOTIONS else DEFAULT_EMOTION


def classify_emotion(text: object) -> str:
    """按关键词把自由文本情绪分到受控枚举；无命中 → neutral。

    评分：每个情绪累计命中关键词数，取最高分；并列时按 _KEYWORDS 顺序（强/负面优先）。
    """
    s = str(text or "")
    if not s.strip():
        return DEFAULT_EMOTION
    best_label = DEFAULT_EMOTION
    best_score = 0
    for label, words in _KEYWORDS:
        score = sum(1 for w in words if w in s)
        if score > best_score:  # 严格大于 → 保留先出现（优先级高）的标签
            best_score = score
            best_label = label
    return best_label


def emotion_scores(text: object) -> Dict[str, int]:
    """调试用：返回各情绪的关键词命中数。"""
    s = str(text or "")
    return {label: sum(1 for w in words if w in s) for label, words in _KEYWORDS}

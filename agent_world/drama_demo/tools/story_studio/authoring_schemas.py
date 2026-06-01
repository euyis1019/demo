"""生成期中间产物 schema（dev_logs/45 §3.2 / dev_logs/48）。区别于运行期 Story Pack schema。

各管理 agent（Casting / Bert 设计师 / Critic）的输出契约——用于 base_agent 的「生成→schema 校验→重试」。
"""

from __future__ import annotations

from typing import Any, Dict, List

import jsonschema

# Bert 设计师：brief + 选角（cast）→ 「条件→反应」规则集（含结局 bert）。剧情结构主载体（取代旧故事图）：
# 玩家做某事(trigger) → 某 NPC(target) 产生某反应(reaction)，经 arms/requires 串成反应链；
# ending 非空的 bert 即结局（触发即收场）。结构不变量（引用闭合/可达/至少一个结局）由 BertSet.validate 兜。
BERT_OUTPUT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["berts"],
    "properties": {
        "berts": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "trigger"],
                "properties": {
                    # id 接受字符串或整数：LLM 常把 bert 编号成 1/2/3（整数），Bert.from_mapping 统一 str() 归一化。
                    "id": {"type": ["string", "integer"]},
                    # 触发条件：玩家做/说了什么（自然语言，运行期由 Bert 导演读对话判命中）
                    "trigger": {"type": "string", "minLength": 1},
                    # 反应：target 这个 NPC 触发后要演什么（非结局 bert 必填）；容错 null（Bert.from_mapping 兜成 ""）
                    "reaction": {"type": ["string", "null"]},
                    # 反应的 NPC（agent_id）；结局 bert 可省略。容错：LLM 偶尔给字符串数字。
                    "target": {"type": ["integer", "string", "null"]},
                    # 可选：仅此地点生效。容错 null（LLM 常对可选字段显式给 null）。
                    "place": {"type": ["string", "null"]},
                    # 触发一次后失效（默认 true）
                    "once": {"type": "boolean"},
                    # 触发后「上膛」的后续 bert id（反应链）——同 id，接受字符串或整数
                    "arms": {"type": "array", "items": {"type": ["string", "integer"]}},
                    # 需先触发过的前置 bert id（空=开局即上膛）——同 id，接受字符串或整数
                    "requires": {"type": "array", "items": {"type": ["string", "integer"]}},
                    # 非空=结局 bert：{kind: good|neutral|bad, summary}
                    "ending": {
                        "type": "object",
                        "required": ["kind"],
                        "properties": {
                            "kind": {"type": "string", "enum": ["good", "neutral", "bad"]},
                            "summary": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}


# Casting：brief + DesignerOutput → 世界原语（角色花名册 + 舞台 + 关系 + 群组）。
CASTING_OUTPUT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["agents", "places"],
    "properties": {
        "agents": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["agent_id", "name", "location"],
                "properties": {
                    "agent_id": {"type": "integer"},
                    "name": {"type": "string"},
                    "location": {"type": "string"},
                    "role": {"type": "string"},
                    "faction": {"type": "string"},
                    "capabilities": {"type": "array", "items": {"type": "string"}},
                    "soul": {"type": "string"},
                    "speech_style": {"type": "string"},  # 说话风格/口头禅/语气，让演员说话有辨识度
                    "inner": {"type": "string"},  # 内心戏：秘密/真实动机/顾忌（不可对玩家明说，但支配言行）
                    "long_term_goal": {"type": "string"},
                    "current_state": {"type": "string"},
                    # 范例对白：2-3 条该角色的典型台词，演员据此学口吻（最强的语气示范信号）
                    "speech_samples": {"type": "array", "items": {"type": "string"}},
                    # 开场第一句：该角色被引入时的定调台词
                    "opening_line": {"type": "string"},
                },
                # 非玩家 agent（agent_id≠0）必须写满核心人设字段，且不得一句话敷衍（minLength 兜底）。
                "allOf": [{
                    "if": {"properties": {"agent_id": {"not": {"const": 0}}}},
                    "then": {
                        "required": ["soul", "speech_style", "inner", "long_term_goal", "current_state"],
                        "properties": {
                            "soul": {"type": "string", "minLength": 16},
                            "speech_style": {"type": "string", "minLength": 8},
                            "inner": {"type": "string", "minLength": 18},
                            "long_term_goal": {"type": "string", "minLength": 4},
                            "current_state": {"type": "string", "minLength": 4},
                        },
                    },
                }],
            },
        },
        "places": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["place_id"],
                "properties": {
                    "place_id": {"type": "string"},
                    "capacity": {"type": "integer"},
                    "attrs": {"type": "object"},
                },
            },
        },
        "coverage": {"type": "array"},
        "relations": {"type": "array"},
        "relation_types": {"type": "array"},
        "groups": {"type": "array"},
    },
}

# Critic：对整包草稿按叙事 rubric 评分 + 给针对性可执行修改意见（结构已合法后的「质量门」）。
CRITIC_OUTPUT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["scores", "casting_feedback", "bert_feedback"],
    "properties": {
        "scores": {
            "type": "object",
            "required": ["character_depth", "voice_distinct", "subtext_drama",
                         "player_agency", "plot_tension"],
            "properties": {
                # 角色深度：soul/inner 具体非套话、inner 与剧情/结局挂钩
                "character_depth": {"type": "integer", "minimum": 1, "maximum": 5},
                # 声音可区分：各 NPC 说话风格彼此可分辨，非通用 AI 腔
                "voice_distinct": {"type": "integer", "minimum": 1, "maximum": 5},
                # 潜台词/戏剧性：directions 有潜台词、反派用算计而非直白敌意
                "subtext_drama": {"type": "integer", "minimum": 1, "maximum": 5},
                # 玩家纳入：分支 condition 互斥且有意义、能体现玩家选择
                "player_agency": {"type": "integer", "minimum": 1, "maximum": 5},
                # 剧情张力：有起承转合/悬念/转折，非平铺直叙
                "plot_tension": {"type": "integer", "minimum": 1, "maximum": 5},
            },
        },
        # 针对 Casting（人设/inner/speech_style/speech_samples/声音区分/反派算计）的可执行修改意见；满意则空串
        "casting_feedback": {"type": "string"},
        # 针对 Bert 反应链（trigger 是否玩家可做到/互不含糊、reaction 是否贴人设、反应链是否连贯、结局是否够分量）的可执行修改意见；满意则空串
        "bert_feedback": {"type": "string"},
        "summary": {"type": "string"},
    },
}


def validate_against(data: Dict[str, Any], schema: Dict[str, Any], *, label: str = "output") -> List[str]:
    """通用 JSON Schema 校验，返回违例列表（空 = 通过）。"""
    validator = jsonschema.Draft202012Validator(schema)
    issues: List[str] = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        issues.append(f"[{label}:{loc}] {err.message}")
    return issues

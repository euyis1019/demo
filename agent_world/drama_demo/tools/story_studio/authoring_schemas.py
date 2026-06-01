"""生成期中间产物 schema（dev_logs/45 §3.2）。区别于运行期 Story Pack schema。

各管理 agent 的输出契约——用于 base_agent 的「生成→schema 校验→重试」。本文件先落
Designer/Producer 的契约（G1/G2 用），Casting/Writer 的在后续切片补。
"""

from __future__ import annotations

from typing import Any, Dict, List

import jsonschema

# Designer：把 brief 编译成故事图骨架（节点/边/结局，不含触发条件细节）。
DESIGNER_OUTPUT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["initial_node", "nodes", "endings", "edges"],
    "properties": {
        "initial_node": {"type": "string", "minLength": 1},
        "nodes": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "beats_label": {"type": "string"},
                    "summary": {"type": "string"},
                },
            },
        },
        "endings": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "kind": {"type": "string", "enum": ["good", "neutral", "bad"]},
                    "summary": {"type": "string"},
                },
            },
        },
        "edges": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "from", "to"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "from": {"type": "string", "minLength": 1},
                    "to": {"type": "string", "minLength": 1},
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

# Writer：DesignerOutput + Casting → 给节点绑注入/地点、给边补触发/动作、产 signals。
WRITER_OUTPUT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["nodes", "edges"],
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "string"},
                    "inject_agents": {"type": "array", "items": {"type": "integer"}},
                    "place_focus": {"type": "string"},
                    "scene_brief": {"type": "string"},  # 这一幕的戏剧情境：此刻在发生什么/张力在哪/玩家处境
                    "directions": {"type": "object"},  # {agent_id: 这一幕该角色的具体表演指引}
                },
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "string"},
                    "condition": {"type": "string"},  # 自然语言：导演据此判断玩家是否推进到该边
                    "actions": {"type": "array"},
                    "legacy_label": {"type": "string"},
                },
            },
        },
        "signals": {"type": "object"},  # 已废弃；导演驱动不再需要关键词/信号
    },
}


# Critic：对整包草稿按叙事 rubric 评分 + 给针对性可执行修改意见（结构已合法后的「质量门」）。
CRITIC_OUTPUT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["scores", "casting_feedback", "writer_feedback"],
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
        # 针对 Writer（scene_brief/directions 潜台词/condition 互斥与玩家纳入/分支张力）的可执行修改意见；满意则空串
        "writer_feedback": {"type": "string"},
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

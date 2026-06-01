"""用户输入契约：semi-structured story brief（dev_logs/45 §2）。

用户只写这一份 brief：premise 自由文本(交 AI 发挥) + 结构化约束(必须遵守、可锁定)。
工作室据此生成整包 Story Pack。本文件给 JSON Schema + 校验函数。
"""

from __future__ import annotations

from typing import Any, Dict, List

import jsonschema

BRIEF_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": True,
    "required": ["player"],
    "properties": {
        "premise": {"type": "string"},
        "tone": {"type": "string"},
        "player": {
            "type": "object",
            "required": ["identity", "role"],
            "properties": {
                "identity": {"type": "string", "minLength": 1},
                "role": {"type": "string", "minLength": 1},
                "is_outsider": {"type": "boolean"},
            },
        },
        "target_acts": {"type": "integer", "minimum": 1, "maximum": 20},
        "target_tasks": {"type": "integer", "minimum": 1, "maximum": 20},  # 任务链长度（任务式生成）；与 target_acts 同义，新词
        "target_nodes": {"type": ["integer", "string"]},
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "faction": {"type": "string"},
                    "is_protagonist": {"type": "boolean"},
                    "personality": {"type": "string"},
                    "appearance": {"type": "string"},
                    "locked": {"type": "boolean"},
                },
            },
        },
        "endings_spec": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "condition_hint": {"type": "string"},
                },
            },
        },
        "constraints": {"type": "array", "items": {"type": "string"}},
        "art_style_hint": {"type": "string"},
        "language_style_hint": {"type": "string"},
    },
}


def validate_brief(brief: Dict[str, Any]) -> List[str]:
    """返回 brief 的校验违例列表（空 = 通过）。"""
    validator = jsonschema.Draft202012Validator(BRIEF_SCHEMA)
    issues: List[str] = []
    for err in sorted(validator.iter_errors(brief), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        issues.append(f"[brief:{loc}] {err.message}")
    return issues

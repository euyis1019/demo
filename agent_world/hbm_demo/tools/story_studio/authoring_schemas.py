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


def validate_against(data: Dict[str, Any], schema: Dict[str, Any], *, label: str = "output") -> List[str]:
    """通用 JSON Schema 校验，返回违例列表（空 = 通过）。"""
    validator = jsonschema.Draft202012Validator(schema)
    issues: List[str] = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        issues.append(f"[{label}:{loc}] {err.message}")
    return issues

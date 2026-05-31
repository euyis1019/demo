"""管理 agent 基类：call_json_with_schema（dev_logs/45 §1.3，对标 AI4VN base_agent）。

单一职责：调 LLM → 抽 JSON → schema 校验 → 失败回灌重试一次 → 仍失败 raise。
LLM 客户端**注入**（client: 可调用 (system, user) -> str），故离线/测试可用 fake client，
不依赖真实网络/key。编排/回路/落盘不在这里（在 orchestrator）。
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List

from agent_world.hbm_demo.tools.story_studio.authoring_schemas import validate_against

# LLM 客户端抽象：给定 system/user prompt，返回模型文本。
LLMClient = Callable[[str, str], str]


class StoryStudioError(Exception):
    """生成期错误（LLM 输出无法解析/校验不过且重试耗尽）。"""


def _extract_json(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        raw = match.group(0)
    return json.loads(raw)


def call_json_with_schema(
    client: LLMClient,
    *,
    system: str,
    user: str,
    schema: Dict[str, Any],
    label: str = "output",
    max_retries: int = 1,
) -> Dict[str, Any]:
    """调 LLM 产 JSON 并按 schema 校验；失败把错误回灌重试，耗尽则抛 StoryStudioError。"""
    feedback = ""
    last_err = ""
    for attempt in range(max_retries + 1):
        prompt = user if not feedback else f"{user}\n\n[上轮输出有问题，请修正]\n{feedback}\n只输出修正后的完整 JSON。"
        text = client(system, prompt)
        try:
            data = _extract_json(text)
        except (json.JSONDecodeError, ValueError) as exc:
            last_err = f"JSON 解析失败：{exc}"
            feedback = last_err
            continue
        issues = validate_against(data, schema, label=label)
        if not issues:
            return data
        last_err = "schema 校验未过：\n" + "\n".join(issues)
        feedback = last_err
    raise StoryStudioError(f"{label} 生成失败（重试 {max_retries} 次）：{last_err}")

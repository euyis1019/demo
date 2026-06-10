"""agent → 引擎的动作返回形状（duck-type 契约，本地复刻不依赖 demo 内部实现）。

引擎 ``WorldStep._extract_actions``（world/step.py）识别
``response.info["tool_calls"]``，每项读 ``tool_name``/``args``。
这里复刻 demo_agent.py 的同形 dataclass —— 不直接 import demo 的
私有下划线符号，避免与引擎自带范例耦合（方案 §4.2 / C2 对策）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ToolCall:
    """一次动作调用：tool_name 严格等于引擎 ActionType.value。"""

    tool_name: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """perform_action_by_llm 的返回；引擎只读 .info["tool_calls"]。"""

    info: Dict[str, Any] = field(default_factory=dict)


def make_response(tool_calls: List[ToolCall]) -> AgentResponse:
    """便捷构造：把动作列表包成引擎认识的响应。"""
    return AgentResponse(info={"tool_calls": tool_calls})


def do_nothing_response() -> AgentResponse:
    """空动作（沉默/发呆）——农场慢节奏下是合法且常见的一拍。"""
    return make_response([ToolCall(tool_name="do_nothing")])

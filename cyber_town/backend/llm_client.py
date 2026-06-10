"""LLM 客户端工厂：真实 AsyncOpenAI 与离线 MockLLMClient 可互换。

两种实现暴露同一调用面 ``client.chat.completions.create(...)``，返回对象
满足 NPC 读取路径：``resp.choices[0].message.{content, tool_calls}``，
其中 tool_call 项有 ``.function.name`` / ``.function.arguments``（JSON str）。

Mock 的用途：
* 网关不可达 / 不想烧 token 时跑通整个世界循环（M0 冒烟）；
* 提供确定性的剧本动作，把 F2F / RDC / GRP / request_move 各通道
  都过一遍（M0 验收 V4）。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from cyber_town.backend.config import LLMConfig

log = logging.getLogger(__name__)


def make_llm_client(cfg: LLMConfig, mock: bool = False) -> Any:
    """构造 LLM 客户端。``mock=True`` 返回离线剧本客户端（零网络）。"""
    if mock:
        log.warning("使用 MockLLMClient（离线剧本模式，不调真实 LLM）")
        return MockLLMClient()
    from openai import AsyncOpenAI  # 延迟 import：mock 路径不依赖 openai

    return AsyncOpenAI(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        timeout=cfg.timeout,
    )


# --------------------------------------------------------------------------- #
# Mock 实现（OpenAI completion 同形对象）                                       #
# --------------------------------------------------------------------------- #


@dataclass
class _MockFunction:
    name: str
    arguments: str  # JSON 字符串，与真实 API 一致


@dataclass
class _MockToolCall:
    function: _MockFunction


@dataclass
class _MockMessage:
    content: Optional[str] = None
    tool_calls: List[_MockToolCall] = field(default_factory=list)


@dataclass
class _MockChoice:
    message: _MockMessage


@dataclass
class _MockCompletion:
    choices: List[_MockChoice]


# 剧本表：(agent_id, t) -> [(tool_name, args), ...]
# 设计目标：8 拍内把 F2F / RDC(跨地点+1拍延迟) / GRP / request_move 全过一遍。
# 配合 --heartbeat 4：老钱(1) 在 t=3,7 激活；阿香(2) 在 t=2,6；大山(3) 异地后 t=5。
_SCRIPT: Dict[Tuple[int, int], List[Tuple[str, Dict[str, Any]]]] = {
    # 大山(3)：开局在 farm 与玩家同场，每拍激活
    (3, 0): [("speak_to_local", {"content": "新邻居，早啊。你这地荒了两年，得先翻一遍土。"})],
    (3, 1): [("update_state", {"new_state": "蹲在田边捏了把土，琢磨着先帮新邻居把东头那垄翻出来。"})],
    (3, 2): [("send_message", {"target": 1, "content": "老钱，新来的农场主要翻地，你店里那把好锄头给他留着。"})],
    (3, 3): [("send_to_group", {"group_id": 100, "content": "各位，新邻居今天开始翻地了，回头都搭把手。"})],
    (3, 4): [("request_move", {"place_id": "square"})],
    (3, 5): [("speak_to_local", {"content": "老钱，锄头呢？给新邻居挑把称手的。"})],
    # 老钱(1)：异地，靠心跳拍激活（heartbeat=4 → t=3,7）
    (1, 3): [("send_message", {"target": 3, "content": "放心，锄头我挑好了，最趁手的那把。让他直接来拿。"})],
    (1, 7): [("update_state", {"new_state": "把留给新农场主的锄头擦了擦，摆在柜台最显眼的位置。"})],
    # 阿香(2)：异地心跳（heartbeat=4 → t=2,6）
    (2, 2): [("update_state", {"new_state": "杯子擦完了，开始切晚上下酒的卤味。"})],
    (2, 6): [("send_to_group", {"group_id": 100, "content": "晚上都来酒馆，给新邻居接风，我请第一轮。"})],
}

_RE_AGENT = re.compile(r"agent_id=(\d+)")
_RE_TICK = re.compile(r"t=(\d+)")


class MockLLMClient:
    """离线剧本客户端：按 (agent_id, t) 查表返回确定性动作。"""

    def __init__(self) -> None:
        self.chat = _MockChat()


class _MockChat:
    def __init__(self) -> None:
        self.completions = _MockCompletions()


class _MockCompletions:
    async def create(self, **kwargs: Any) -> _MockCompletion:
        """从 user 消息里解析 agent_id 与 tick，查剧本表出动作。"""
        user_text = ""
        for m in kwargs.get("messages", []):
            if m.get("role") == "user":
                user_text = m.get("content", "")
        aid_m = _RE_AGENT.search(user_text)
        t_m = _RE_TICK.search(user_text)
        aid = int(aid_m.group(1)) if aid_m else -1
        t = int(t_m.group(1)) if t_m else -1

        entries = _SCRIPT.get((aid, t), [])
        tool_calls = [
            _MockToolCall(_MockFunction(name, json.dumps(args, ensure_ascii=False)))
            for name, args in entries
        ]
        if not tool_calls:
            # 没有剧本 → 沉默发呆（农场慢节奏的合法一拍）
            tool_calls = [_MockToolCall(_MockFunction("do_nothing", "{}"))]
        return _MockCompletion(choices=[_MockChoice(_MockMessage(tool_calls=tool_calls))])

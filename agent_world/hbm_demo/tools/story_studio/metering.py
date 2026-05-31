"""生成期计量：成本护栏 + 生成 trace（dev_logs/45 §7 / dev_logs/46 D-7/D-8）。

透明地包住注入的 LLM 客户端：每次调用先过预算护栏(超限即停)，再记一条 trace(可重建生成
决策链)，最后委托真实 client。base_agent/各 agent 零改动——orchestrator 在传入前包一层即可。
不含时间戳(保持测试确定性)；要时间戳由调用方在 trace 落盘时补。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List

from agent_world.hbm_demo.tools.story_studio.base_agent import LLMClient, StoryStudioError


class BudgetExceededError(StoryStudioError):
    """生成期 LLM 调用次数超出预算护栏。"""


@dataclass
class TraceEntry:
    index: int
    system_len: int
    user_len: int
    output_len: int


@dataclass
class GenerationTrace:
    """生成决策链记录：每次 LLM 调用一条（用于可观测/审计/成本估算）。"""

    entries: List[TraceEntry] = field(default_factory=list)

    @property
    def calls(self) -> int:
        return len(self.entries)

    @property
    def total_output_chars(self) -> int:
        return sum(e.output_len for e in self.entries)

    def summary(self) -> str:
        return f"LLM 调用 {self.calls} 次，产出共 {self.total_output_chars} 字符"


def metering_client(
    client: LLMClient,
    *,
    max_calls: int | None = None,
    trace: GenerationTrace | None = None,
) -> LLMClient:
    """把 client 包成"先护栏、再记 trace、后委托"的计量客户端。"""
    counter = {"n": 0}

    def _call(system: str, user: str) -> str:
        if max_calls is not None and counter["n"] >= max_calls:
            raise BudgetExceededError(f"生成期 LLM 调用超出预算护栏（max_calls={max_calls}）")
        counter["n"] += 1
        text = client(system, user)
        if trace is not None:
            trace.entries.append(
                TraceEntry(index=counter["n"], system_len=len(system), user_len=len(user), output_len=len(text or ""))
            )
        return text

    return _call

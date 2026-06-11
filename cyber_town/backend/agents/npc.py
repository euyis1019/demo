"""CyberTownNPC —— LLM 驱动的村民 agent（DemoAgent 同形，农场生活化版）。

与引擎自带 DemoAgent 的差异（方案 D10/D18 + 审计结论）：

* **允许沉默**：提示词不强推剧情，do_nothing / 只干活不说话是合法常态；
* **无硬性 update_state 强制拍**：只保留软提醒（状态陈旧 ≥6 拍）；
* **单次 LLM 调用超时**（asyncio.wait_for）：超时该拍降级 do_nothing，
  不拖垮世界节奏（方案 §5.2 变速拍对策）；
* **私有工具拦截挂点**：``private_tool_handler`` 处理引擎不认识的工具
  （如 M4 的 adjust_affinity——dispatcher 对未知 action 会静默丢弃，
  必须在返回引擎前抽走，见方案 §9）；
* **提示词第 6 段挂点**：``prompt_suffix_provider`` 在 perception 5 段
  之后追加（M4 注入好感度段），不动引擎前 5 段。

W6 起所有提示词文本（工具 schema / 观察渲染 / 纪律）集中在
cyber_town/backend/prompts/，本文件只剩决策流程与解析逻辑。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from cyber_town.backend.agents.actions import AgentResponse, ToolCall, make_response
from cyber_town.backend.prompts.npc_tools import TOOLS
from cyber_town.backend.prompts.observation import render_observation

log = logging.getLogger(__name__)


@dataclass
class CyberTownNPC:
    """轻量村民 agent：满足 WorldStep duck-type 契约 + 生活化观察渲染。"""

    agent_id: int
    name: str
    soul: str = ""
    long_term_goal: str = ""
    current_state: str = ""
    current_state_set_at: int = 0
    short_term_goal: str = ""
    last_message_seen_at: int = -1
    groups: List[Dict[str, Any]] = field(default_factory=list)

    # ---- 装配期注入（world_factory 负责；可空字段显式 Optional）----
    name_directory: Dict[int, str] = field(default_factory=dict)
    available_places: List[str] = field(default_factory=list)
    perception_builder: Optional[Any] = None
    segment_store: Optional[Any] = None
    client: Optional[Any] = None            # AsyncOpenAI 或 MockLLMClient
    model: str = "deepseek-v4-flash"
    temperature: float = 0.8
    # None = 不传 max_tokens（用 API 默认上限）——W6 用户拍板：放开输出预算，
    # 防 reasoning 模型思维链挤占答案额度导致截断
    max_tokens: Optional[int] = None
    # W8：禁思维链（见 config.LLMConfig.disable_thinking 注释——tool_calls 稳定性 + 提速）
    disable_thinking: bool = True
    llm_timeout: float = 20.0               # 单次调用超时（变速拍对策）
    # 世界时间显示映射（纯叙事，不影响内核 tick）
    wall_start_time: str = "08:00"
    minutes_per_tick: int = 5

    # ---- 扩展挂点（M4 好感度等，保持解耦）----
    # 追加给 LLM 的额外工具 schema（如 adjust_affinity——引擎不认识的私有工具
    # 必须同时登记进 private_tool_names，否则会被 dispatcher 静默丢弃）
    extra_tools: List[Dict[str, Any]] = field(default_factory=list)
    # 第 6 段提示词：fn(npc, obs) -> str；返回空串则不追加
    prompt_suffix_provider: Optional[Callable[["CyberTownNPC", Any], str]] = None
    # 第 7 段（W5 世界事件导演）：fn(t) -> str；环境事实注入，空串不追加
    world_event_provider: Optional[Callable[[int], str]] = None
    # 私有工具：引擎不认识的 tool（dispatcher 会静默丢弃），返回前在此拦截。
    # handler 调用约定：fn(npc, tool_name, args, t) -> None（异常会被吞并告警）
    private_tool_names: frozenset = frozenset()
    private_tool_handler: Optional[
        Callable[["CyberTownNPC", str, Dict[str, Any], int], None]
    ] = None

    # ------------------------------------------------------------------ #
    # 引擎入口：一拍一次决策                                                #
    # ------------------------------------------------------------------ #

    async def perform_action_by_llm(self, world: Any, t: int) -> AgentResponse:
        """感知 → LLM 决策 → 拦截私有工具 → 返回标准动作（fail-soft）。"""
        if self.perception_builder is None or self.client is None:
            return make_response([ToolCall("do_nothing")])

        try:
            sys_prompt, obs = await self.perception_builder.build(self, world, t)
        except Exception as exc:  # noqa: BLE001 — 感知失败不阻断世界
            log.error("NPC %s 感知失败 t=%s：%s", self.agent_id, t, exc)
            return make_response([ToolCall("do_nothing")])

        # 第 6 段挂点（M4 好感度）：在引擎 5 段之后追加，不动前 5 段
        if self.prompt_suffix_provider is not None:
            try:
                suffix = self.prompt_suffix_provider(self, obs)
                if suffix:
                    sys_prompt = sys_prompt + "\n\n" + suffix
            except Exception as exc:  # noqa: BLE001 — 挂点异常跳过拼接
                log.warning("NPC %s 第6段拼接失败：%s", self.agent_id, exc)
        # 第 7 段挂点（W5 世界事件）：环境事实，如何反应全由 LLM
        if self.world_event_provider is not None:
            try:
                ev = self.world_event_provider(t)
                if ev:
                    sys_prompt = sys_prompt + "\n\n" + ev
            except Exception as exc:  # noqa: BLE001
                log.warning("NPC %s 第7段拼接失败：%s", self.agent_id, exc)

        user_text = render_observation(self, obs, t)
        kwargs: Dict[str, Any] = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_text},
            ],
            tools=TOOLS + self.extra_tools,
            tool_choice="auto",
            temperature=self.temperature,
        )
        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens
        if self.disable_thinking:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            resp = await asyncio.wait_for(
                self.client.chat.completions.create(**kwargs),
                timeout=self.llm_timeout,
            )
        except asyncio.TimeoutError:
            log.warning("NPC %s LLM 超时（>%ss）t=%s，本拍发呆", self.agent_id, self.llm_timeout, t)
            return make_response([ToolCall("do_nothing")])
        except Exception as exc:  # noqa: BLE001 — 单次调用失败不阻断世界
            log.error("NPC %s LLM 调用失败 t=%s：%s", self.agent_id, t, exc)
            return make_response([ToolCall("do_nothing")])

        # W8 格式纠错重试（不丢话保险）：模型偶发把答话写进 content 而不调工具，
        # 这话会被当独白丢弃（「不回复」的隐性来源之一）。同拍追问一次让它
        # 自己改用工具——说不说/说什么仍 100% 由 LLM 决定，只纠输出格式。
        resp = await self._retry_if_silent_with_content(resp, kwargs, t)
        return self._extract_tool_calls(resp, t)

    async def _retry_if_silent_with_content(
        self, resp: Any, kwargs: Dict[str, Any], t: int
    ) -> Any:
        """无 tool_calls 但 content 非空 → 带纠错提示重试一次（10s 限时，失败用原响应）。"""
        try:
            msg = resp.choices[0].message
        except (AttributeError, IndexError):
            return resp
        content = (getattr(msg, "content", None) or "").strip()
        if (getattr(msg, "tool_calls", None) or []) or not content:
            return resp
        retry_kwargs = dict(kwargs)
        retry_kwargs["messages"] = list(kwargs["messages"]) + [
            {"role": "assistant", "content": content},
            {"role": "user", "content": (
                "（系统提示）你刚才只输出了文字、没有调用任何工具——这段话没有"
                "进入世界，别人听不见。若这是想说出口的话/想做的事，请重新用"
                "对应工具表达（speak_to_local / send_message / update_state…）；"
                "若你确实想安静过这一拍，调用 do_nothing。"
            )},
        ]
        try:
            retried = await asyncio.wait_for(
                self.client.chat.completions.create(**retry_kwargs), timeout=10.0,
            )
            if getattr(retried.choices[0].message, "tool_calls", None):
                log.info("NPC %s t=%s 格式纠错重试成功（content→工具）", self.agent_id, t)
                return retried
        except Exception as exc:  # noqa: BLE001 — 重试失败不影响原响应路径
            log.warning("NPC %s t=%s 格式纠错重试失败：%s", self.agent_id, t, exc)
        return resp

    # ------------------------------------------------------------------ #
    # LLM 响应解析 + 私有工具拦截                                            #
    # ------------------------------------------------------------------ #

    def _extract_tool_calls(self, resp: Any, t: int) -> AgentResponse:
        """解析 tool_calls；私有工具（如 adjust_affinity）拦截后不进引擎。"""
        try:
            msg = resp.choices[0].message
        except (AttributeError, IndexError):
            return make_response([ToolCall("do_nothing")])

        engine_calls: List[ToolCall] = []
        for tc in (getattr(msg, "tool_calls", None) or []):
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
                if not isinstance(args, dict):
                    args = {}
            except json.JSONDecodeError:
                args = {}
            # 私有工具：引擎 dispatcher 不认识会静默丢弃 → 必须在这里截走
            if name in self.private_tool_names:
                if self.private_tool_handler is not None:
                    try:
                        self.private_tool_handler(self, name, args, t)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("私有工具 %s 处理失败：%s", name, exc)
                continue
            engine_calls.append(ToolCall(tool_name=name, args=args))

        if not engine_calls:
            content = (getattr(msg, "content", None) or "").strip()
            if content:
                log.info("NPC %s 内心独白：%s", self.agent_id, content[:120])
            engine_calls = [ToolCall("do_nothing")]
        return make_response(engine_calls)

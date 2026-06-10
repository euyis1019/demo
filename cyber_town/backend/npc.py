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
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from cyber_town.backend.actions import AgentResponse, ToolCall, make_response

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 工具 schema（OpenAI tool-calls 规范）——名字严格等于引擎 ActionType.value      #
# --------------------------------------------------------------------------- #

TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "speak_to_local",
            "description": (
                "对当前地点里所有人当面说出口的话（同地点广播，在场的人都听见）。"
                "是『口语』不是『短信腔』：像街坊当面唠嗑那样说话，"
                "称呼随口、说事直接。适合：寒暄、唠家常、招呼客人、当面答话。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "你说出口的话，1-3 句，口语。",
                    }
                },
                "required": ["content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": (
                "给某个具体的人发私信（手机短信/微信，对方不在身边也能收到，"
                "异地约 1 拍后送达）。悄悄话、捎话、远程招呼用这个；"
                "对方就在你眼前时优先当面说（speak_to_local）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "integer", "description": "收件人 agent_id"},
                    "content": {"type": "string"},
                },
                "required": ["target", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_to_group",
            "description": (
                "在你所在的群聊里发消息，群成员下一拍能看到。"
                "适合：跟全镇人说事、张罗活动、群里搭话。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer"},
                    "content": {"type": "string"},
                },
                "required": ["group_id", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_move",
            "description": (
                "走去另一个地点（本拍末出发，下一拍人在新地点）。"
                "按你的生活作息走动：串门、采买、收工去酒馆。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "place_id": {"type": "string", "description": "目的地 place_id"},
                },
                "required": ["place_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_state",
            "description": (
                "更新自己的『当前状态』（你正在做什么/心里在想什么）。"
                "干活、歇着、心情变化都可以用它记录——不说话的拍子里，"
                "用它让别人看见你在过日子。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "new_state": {
                        "type": "string",
                        "description": "新的状态描述，1-2 句。",
                    },
                },
                "required": ["new_state"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_short_term_goal",
            "description": (
                "更新自己的『当前小目标』（接下来一小段时间打算干嘛）。"
                "发现自己在原地打转/重复说同样的话时，先调它再行动。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "new_goal": {
                        "type": "string",
                        "description": "1-2 句，明确下一步。",
                    },
                },
                "required": ["new_goal"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "do_nothing",
            "description": (
                "这一拍安静过：发呆、继续手头的活、晒太阳。"
                "乡下日子慢，没事不必硬找话——这是完全正常的选择。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
]


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
    max_tokens: int = 400
    llm_timeout: float = 20.0               # 单次调用超时（变速拍对策）
    # 世界时间显示映射（纯叙事，不影响内核 tick）
    wall_start_time: str = "08:00"
    minutes_per_tick: int = 5

    # ---- 扩展挂点（M4 好感度等，保持解耦）----
    # 第 6 段提示词：fn(npc, obs) -> str；返回空串则不追加
    prompt_suffix_provider: Optional[Callable[["CyberTownNPC", Any], str]] = None
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

        user_text = self._observation_to_text(obs, t)
        try:
            resp = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_text},
                    ],
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                ),
                timeout=self.llm_timeout,
            )
        except asyncio.TimeoutError:
            log.warning("NPC %s LLM 超时（>%ss）t=%s，本拍发呆", self.agent_id, self.llm_timeout, t)
            return make_response([ToolCall("do_nothing")])
        except Exception as exc:  # noqa: BLE001 — 单次调用失败不阻断世界
            log.error("NPC %s LLM 调用失败 t=%s：%s", self.agent_id, t, exc)
            return make_response([ToolCall("do_nothing")])

        return self._extract_tool_calls(resp, t)

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

    # ------------------------------------------------------------------ #
    # 观察渲染（生活化版 user prompt）                                       #
    # ------------------------------------------------------------------ #

    def _label(self, agent_id: Any) -> str:
        try:
            aid = int(agent_id)
        except (TypeError, ValueError):
            return str(agent_id)
        name = self.name_directory.get(aid)
        return f"{name}(agent_{aid})" if name else f"agent_{aid}"

    def _wall_clock_label(self, t: int) -> str:
        """tick → 'HH:MM'（解析失败返回空串，提示词优雅降级）。"""
        try:
            h, m = self.wall_start_time.split(":")
            base_min = int(h) * 60 + int(m)
        except (ValueError, AttributeError):
            return ""
        total = (base_min + int(t) * int(self.minutes_per_tick)) % (24 * 60)
        return f"{total // 60:02d}:{total % 60:02d}"

    def _observation_to_text(self, obs: Any, t: int) -> str:
        lines: List[str] = []
        wall = self._wall_clock_label(t)
        wall_tag = f" 世界时间 {wall}" if wall else ""
        lines.append(f"# 当前 tick：t={t}{wall_tag}（每拍约 {self.minutes_per_tick} 分钟）")

        # 状态陈旧软提醒（无硬性强制——农场慢节奏）
        stale = int(t) - int(getattr(self, "current_state_set_at", 0) or 0)
        if stale >= 6:
            lines.append(
                f"# ⚠ 你的『当前状态』已 {stale} 拍没更新，若手头的事/位置/心境"
                "已变化，找机会 update_state 写一句新的。"
            )

        lines.append(f"# 你是：agent_id={self.agent_id}（{self.name}）")
        lines.append(f"# 你现在的位置：{obs.self_location}")

        briefs = list(getattr(obs, "available_places_brief", []) or [])
        if briefs:
            lines.append("# 可以走去的其他地点（request_move，严格用以下 place_id）：")
            for b in briefs:
                summary = (getattr(b, "summary", "") or "").strip()
                tail = f" —— {summary}" if summary else ""
                lines.append(f"  - {b.place_id}{tail}")
                occupants = getattr(b, "occupants", None)
                if occupants:
                    occ = "、".join(self._label(o) for o in occupants)
                    lines.append(f"    现在在那儿的人：{occ}")
        elif self.available_places:
            others = [p for p in self.available_places if p != obs.self_location]
            if others:
                lines.append("# 可以走去的其他地点：" + "、".join(others))

        co = list(obs.co_located_agents or [])
        if co:
            lines.append(
                "# 同地点的人（speak_to_local 当面说话他们都听见）："
                + "、".join(self._label(a) for a in co)
            )
        else:
            lines.append("# 同地点的人：没人——当面说话没人听见，自己干自己的就好")

        arrivals = list(getattr(obs, "recent_arrivals", []) or [])
        departures = list(getattr(obs, "recent_departures", []) or [])
        if arrivals:
            lines.append("# 刚走进来：" + "、".join(self._label(a) for a in arrivals))
        if departures:
            lines.append("# 刚离开：" + "、".join(self._label(a) for a in departures))

        if obs.contacts:
            cs = []
            for c in obs.contacts:
                reach = "可达" if c.can_reach_now else "不可达"
                rels = list(getattr(c, "relation_types", []) or [])
                rel = "、".join(rels) if rels else "认识"
                cs.append(f"{self._label(c.agent_id)}[{rel}|{reach}]")
            lines.append("# 你的联系人（send_message 发私信）：" + "、".join(cs))

        if self.groups:
            lines.append("# 你所在的群（send_to_group 在群里说话）：")
            for g in self.groups:
                lines.append(
                    f"  - group_id={g['group_id']} 名称={g.get('name')!r} "
                    f"成员={g.get('members', [])}"
                )

        if obs.incoming_messages:
            lines.append("# 你收到的消息：")
            for m in obs.incoming_messages:
                ch = getattr(m, "channel_type", "?")
                gid = getattr(m, "group_id", None)
                tag = ch + (f"#g{gid}" if gid else "")
                lines.append(
                    f"  - [{tag}] 来自 {self._label(getattr(m, 'sender_id', None))}："
                    f"{getattr(m, 'content', '')}"
                )

        f2f_history = list(getattr(obs, "f2f_local_history", []) or [])
        if f2f_history:
            current_here = set(obs.co_located_agents or []) | {self.agent_id}
            lines.append("# 本地最近的当面对话（按时间序，含你自己说过的）：")
            for at_t, sender, _mid, content in f2f_history:
                tag = "" if sender in current_here else "[已离开]"
                lines.append(f"  - t={at_t} {self._label(sender)}{tag}：{content}")

        if obs.overheard:
            lines.append("# 你旁听到的（不是说给你的，但你在场）：")
            for o in obs.overheard:
                lines.append(f"  - {getattr(o, 'content', '')}")

        if obs.recent_failed_attempts:
            lines.append(
                f"# 上一拍你有 {len(obs.recent_failed_attempts)} 条消息没送到"
                "（对方不可达）。"
            )

        if obs.group_events:
            lines.append("# 群里的动静：")
            for ge in obs.group_events:
                lines.append(
                    f"  - {getattr(ge, 'event_type', '?')} "
                    f"{self._label(getattr(ge, 'agent_id', '?'))} "
                    f"在 group_{getattr(ge, 'group_id', '?')}"
                )

        my_recent = self._recent_self_actions(limit=4)
        if my_recent:
            lines.append("# 你自己最近做过的（别车轱辘重复同样的话/动作）：")
            for entry in my_recent:
                lines.append(f"  - t={entry['t']} {entry['summary']}")

        lines.append("")
        lines.append(
            "【这一拍怎么过】\n"
            "乡下日子慢，按你的人设和作息自然地过：\n"
            "  • 有人跟你说话/有事发生 → 自然回应，别已读不回太多拍。\n"
            "  • 没事的时候 → do_nothing 发呆、或 update_state 记一笔手头的活，\n"
            "    都是完全正常的选择，不必硬找话。\n"
            "  • 想串门/采买/收工喝一杯 → request_move 走过去。\n"
            "  • 别和『你自己最近做过的』雷同——同一句话别翻来覆去说。\n"
            "  • 当面说是口语（speak_to_local）；人不在身边才发私信（send_message）。\n"
            "通常一拍调用 1 个工具；说话同时想换状态可以带上 update_state（最多 2 个）。\n"
            "保持人物性格，像个真住在镇上的人。"
        )
        return "\n".join(lines)

    def _recent_self_actions(self, limit: int = 4) -> List[Dict[str, Any]]:
        """从 segment_store 读自己最近的动作（防 loop 的关键上下文）。"""
        if self.segment_store is None:
            return []
        try:
            entries = self.segment_store.get(self.agent_id) or []
        except Exception:  # noqa: BLE001
            return []
        out: List[Dict[str, Any]] = []
        for e in entries[-limit:]:
            kind = getattr(e, "kind", "")
            payload = getattr(e, "payload", {}) or {}
            t_e = getattr(e, "t", "?")
            if kind == "speak_to_local":
                summary = f"当面说：{payload.get('content', '')}"
            elif kind == "send_message":
                summary = f"私信 {self._label(payload.get('target'))}：{payload.get('content', '')}"
            elif kind == "send_to_group":
                summary = f"群聊(g{payload.get('group_id')})：{payload.get('content', '')}"
            elif kind == "request_move":
                summary = f"动身去 {payload.get('place_id')}"
            elif kind == "update_state":
                summary = f"状态：{payload.get('new_state', '')}"
            elif kind == "update_short_term_goal":
                summary = f"小目标：{payload.get('new_goal', '')}"
            elif kind == "do_nothing":
                summary = "发呆/干自己的活"
            else:
                summary = f"{kind} {payload}"
            out.append({"t": t_e, "summary": summary[:160]})
        return out

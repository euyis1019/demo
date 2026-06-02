"""LLM-backed agent for drama demo — extends DemoAgent with script/memory hooks."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent_world.demo.demo_agent import (
    DemoAgent,
    TOOLS as DEMO_TOOLS,
    _Response,
    _ToolCall,
)

log = logging.getLogger(__name__)

RELATION_CHANGE_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "relation_change",
        "description": (
            "修改你与另一 agent 之间的社交关系（商业盟友、上下级等）。"
            "create=建立关系，break=断绝关系。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "integer", "description": "目标 agent_id"},
                "relation_type": {
                    "type": "string",
                    "description": "关系类型，如 business_partner / ally",
                },
                "op": {
                    "type": "string",
                    "enum": ["create", "break"],
                    "description": "create=建立，break=断绝",
                },
            },
            "required": ["target", "relation_type", "op"],
            "additionalProperties": False,
        },
    },
}

DRAMA_TOOLS: List[Dict[str, Any]] = list(DEMO_TOOLS) + [RELATION_CHANGE_TOOL]

_DEMO_TAIL_MARKER = "【本拍硬性要求】"

_DRAMA_TOOLS_LIST = (
    "  • speak_to_local           —— 当面说话（只对同地点的人有效）\n"
    "  • send_message             —— 私信某个 agent_id（1 拍后到达）\n"
    "  • send_to_group            —— 在群里说话（你必须是群成员）\n"
    "  • update_state             —— 改写自己的当前内心状态\n"
    "  • do_nothing               —— 真的无话可说时才用\n"
    "  • relation_change          —— 建立/断绝关系（仅剧情允许时）"
)


def _adapt_relation_change_args(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(kwargs)
    if "target" in out:
        out["dst"] = out.pop("target")
    op = out.get("op")
    if op == "break":
        out["op"] = "remove"
    elif op == "create":
        out["op"] = "add"
    return out


@dataclass
class DramaAgent(DemoAgent):
    """HBM scenario agent with DialogueInjection memory + relation_change tool."""

    player_memory: List[Dict[str, str]] = field(default_factory=list)
    completion_extras: Dict[str, Any] = field(default_factory=dict)
    _pending_rdc_out: Dict[int, int] = field(default_factory=dict, repr=False)
    _inject_responded: bool = field(default=False, repr=False)

    async def update_memory(
        self,
        content: Optional[str] = None,
        role: str = "system",
        message: Any = None,
        **kwargs: Any,
    ) -> None:
        if content is None and message is not None:
            content = getattr(message, "content", None) or str(message)
        if content is None:
            content = kwargs.get("text", "")
        self.player_memory.append(
            {"role": str(role), "content": str(content).strip()}
        )

    async def perform_action_by_llm(self, world: Any, t: int) -> _Response:
        if self.perception_builder is None or self.client is None:
            return _Response(info={"tool_calls": []})

        try:
            sys_prompt, obs = await self.perception_builder.build(self, world, t)
        except Exception as exc:  # noqa: BLE001
            log.error("agent %s perception failed: %s", self.agent_id, exc)
            return _Response(info={"tool_calls": []})

        user_text = self._observation_to_text(obs, t, world=world)
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_text},
        ]

        turn_ctx = getattr(self, "_batch_turn_context", None) or {}
        temperature = float(
            getattr(self, "_batch_temperature", None)
            if getattr(self, "_batch_temperature", None) is not None
            else self.temperature
        )
        max_tokens = int(
            getattr(self, "_batch_max_tokens", None)
            if getattr(self, "_batch_max_tokens", None) is not None
            else self.max_tokens
        )

        trace_id: Optional[str] = None
        world_db = getattr(world, "world_db", None)
        from agent_world.drama_demo.core.runner.integration import abcs
        from agent_world.drama_demo.core.runner.integration import prompt_trace

        trace_store = prompt_trace.PromptTraceStore(world_db) if world_db is not None else None
        skip_idle_trace = (
            abcs.is_world_loop_enabled()
            and turn_ctx.get("player_inject_tick") is None
        )
        if trace_store is not None and trace_store.enabled and not skip_idle_trace:
            trace_id = trace_store.begin_trace(
                agent_id=int(self.agent_id),
                at_tick=int(t),
                phase=None,
                player_turn=(
                    int(turn_ctx["player_turn"])
                    if turn_ctx.get("player_turn") is not None
                    else None
                ),
                model=str(self.model),
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=sys_prompt,
                user_prompt=user_text,
            )
            self._prompt_trace_id = trace_id  # noqa: SLF001

        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=DRAMA_TOOLS,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
                **self.completion_extras,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("agent %s LLM call failed: %s", self.agent_id, exc)
            self._prompt_trace_id = None  # noqa: SLF001
            return _Response(info={"tool_calls": []})

        msg = resp.choices[0].message
        tool_calls: List[_ToolCall] = []
        raw_tool_calls: List[Dict[str, Any]] = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
                if not isinstance(args, dict):
                    args = {}
            except json.JSONDecodeError:
                args = {}
            name = tc.function.name
            if name == "relation_change":
                args = _adapt_relation_change_args(args)
            tool_calls.append(_ToolCall(tool_name=name, args=args))
            raw_tool_calls.append({"name": name, "args": args})

        if trace_store is not None and trace_id:
            trace_store.finish_trace(
                trace_id,
                tool_calls=raw_tool_calls,
                assistant_content=(msg.content or "").strip() or None,
            )

        if not tool_calls:
            content = (msg.content or "").strip()
            if content:
                log.info("agent %s thought: %s", self.agent_id, content[:200])
            tool_calls = [_ToolCall(tool_name="do_nothing", args={})]

        return _Response(info={"tool_calls": tool_calls})

    def _short_action_rules(self) -> str:
        """通用（数据驱动）的本回合行动要求——人设/剧情来自活跃 Story Pack 的知识块，这里只给跨故事
        通用的行动纪律。不含任何写死的故事/阶段/角色编号规则（换 config 即换游戏）。"""
        # NPC 可按自己的角色意图真实移动（request_move 已不再被引擎吞）——但务必「言行一致」：
        # 说要去某处就真的 move 过去，别只动嘴不动身；也别明明没动却说自己走了。非必要不挪窝。
        move_rule = (
            "2) 你**可以 request_move 到相邻地点**，由你自行判断是否需要（要去查个东西/躲开/追随某人/离场等）——"
            "但**非必要不挪窝**，守在该守的地方。\n"
            "   ★**言行必须一致**：台词里说了「我去/我走/到那边」，这一拍就**真的 request_move 过去**；"
            "不打算动就别在台词里说自己走了。\n"
        )

        # 只保留跨故事的「工具/消息时序」引擎机制；**何时开口/何时沉默/怎么演/如何推进**由管理 agent 经
        # acting_guide 生成进 meta.acting_guide，运行期由 knowledge.py 注入——引擎不再硬性「每拍必回应」
        # （旧硬规则会盖过 acting_guide 的沉默纪律，导致 NPC 太活跃、刷屏、不推进剧情）。
        return (
            "【本回合怎么行动——按你的角色处境与上文「表演须知」自己判断，别机械执行】\n"
            "（以下是跨故事的通用行动纪律；**若与上文你的「表演须知」(acting_guide) 有出入，一律以「表演须知」为准**——"
            "那才是为你这个角色量身调教的。）\n"
            "1) 这一拍**开不开口、说什么、还是沉默(do_nothing)，由你自己判断**——别为刷存在感硬接话：\n"
            "   · 玩家直接对你说话时一般应当回应（别无视玩家）：当面 speak_to_local、私信 send_message；\n"
            "   · NPC 之间不必每拍都搭话——这一拍你没有要紧的话/事、或只会重复别人，就 do_nothing，把舞台让给该说的人；\n"
            "   · 一旦开口就**带着你的目的推进这一幕**（追问/试探/施压/交代或验收任务/揭露），别寒暄注水、别原地打转。\n"
            f"{move_rule}"
            "3) 每一拍只调用一个工具，参数严格符合 schema。\n"
            "4) 有未读私信(RDC)：通常该回就回，但回不回、何时回由你按角色与处境定，不必为回而回。\n"
            "\n可选工具：\n"
            f"{_DRAMA_TOOLS_LIST}"
        )

    def _replace_demo_tail(self, text: str) -> str:
        idx = text.find(_DEMO_TAIL_MARKER)
        head = text[:idx].rstrip() if idx >= 0 else text.rstrip()
        return head + "\n\n" + self._short_action_rules()

    def _observation_to_text(self, obs: Any, t: int, *, world: Any = None) -> str:
        prefix: List[str] = []

        if self.player_memory:
            prefix.append("# 玩家/系统注入的对话记忆（本批首次须回应；已回应后勿重复）：")
            for entry in self.player_memory:
                prefix.append(f"  - [{entry['role']}] {entry['content']}")

        scripted = getattr(obs, "scripted_notification", None)
        if scripted:
            prefix.append("# 剧本通知：")
            if isinstance(scripted, list):
                for item in scripted:
                    prefix.append(f"  - {item}")
            else:
                prefix.append(f"  - {scripted}")

        world_db = getattr(world, "world_db", None) if world is not None else None

        if world_db is not None:
            from agent_world.drama_demo.core.runner.integration import abcs
            from agent_world.drama_demo.core.runner.integration.session import (
                get_name_map,
            )

            recap = abcs.build_thread_recap(
                int(self.agent_id),
                int(t),
                world_db,
                get_name_map(),
            )
            if recap:
                prefix.append(recap)

        from agent_world.drama_demo.core.runner.integration import abcs

        hints = abcs.build_conversation_hints(int(self.agent_id), self, world, int(t))
        if hints:
            prefix.append(hints)

        # 始终压制基类「≥5 拍未动就强制本拍只能 update_state」这条引擎硬规则——
        # 何时改写内心状态由 actor 自决（acting_guide 指导），引擎不强夺本拍。
        # （A8 起 inject 路径已压制；此处对空闲路径一并压制，去掉残留的强制 update_state 硬规则。）
        saved_set_at = int(getattr(self, "current_state_set_at", 0) or 0)
        self.current_state_set_at = int(t)
        try:
            base = super()._observation_to_text(obs, t)
        finally:
            self.current_state_set_at = saved_set_at
        if (
            self.player_memory
            or getattr(obs, "scripted_notification", None)
            or getattr(self, "_batch_turn_context", None)
        ):
            base = self._replace_demo_tail(base)

        if prefix:
            return "\n".join(prefix) + "\n\n" + base
        return base

"""LLM-backed agent for HBM demo — extends DemoAgent with script/memory hooks."""

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

HBM_TOOLS: List[Dict[str, Any]] = list(DEMO_TOOLS) + [RELATION_CHANGE_TOOL]

_DEMO_TAIL_MARKER = "【本拍硬性要求】"

_HBM_TOOLS_LIST = (
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
class HbmAgent(DemoAgent):
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
        from agent_world.hbm_demo.core.runner.integration import abcs
        from agent_world.hbm_demo.core.runner.integration import prompt_trace

        trace_store = prompt_trace.PromptTraceStore(world_db) if world_db is not None else None
        skip_idle_trace = (
            abcs.is_world_loop_enabled()
            and turn_ctx.get("player_inject_tick") is None
        )
        if trace_store is not None and trace_store.enabled and not skip_idle_trace:
            trace_id = trace_store.begin_trace(
                agent_id=int(self.agent_id),
                at_tick=int(t),
                phase=str(turn_ctx.get("phase") or "") or None,
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
                tools=HBM_TOOLS,
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
        from agent_world.hbm_demo.shared.story_pack.scenario_adapter import (
            is_free_move_enabled,
        )

        if is_free_move_enabled():
            move_rule = (
                "2) 你可以 request_move 到相邻地点，由你自行判断是否需要（如被叫去某处、追随某人）；"
                "台词须与移动一致。\n"
            )
        else:
            move_rule = (
                "2) request_move 被引擎忽略，台词里不要说「我去某处」——位置不会变。\n"
            )

        # 只保留跨故事的「工具/消息时序」引擎机制；「怎么演」（口吻/句长/风格/沉默纪律）由管理 agent
        # 经 acting_guide 生成进 meta.acting_guide，运行期由 knowledge.py 注入，引擎不再写死表演规则。
        return (
            "【本回合行动要求】\n"
            "1) 有玩家/他人对你说话时，本拍先回应（当面用 speak_to_local，私信用 send_message）；"
            "已回应且无新消息时可 do_nothing。\n"
            f"{move_rule}"
            "3) 每一拍只调用一个工具，参数严格符合 schema。\n"
            "4) 有未读私信(RDC)时本拍须 send_message 回复发件人，不要拖延；"
            "无未读、无新消息、本批已说过话 → 可 do_nothing。\n"
            "\n可选工具：\n"
            f"{_HBM_TOOLS_LIST}"
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
            from agent_world.hbm_demo.core.runner.integration import abcs
            from agent_world.hbm_demo.core.runner.integration.session import (
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

        from agent_world.hbm_demo.core.runner.integration import abcs

        hints = abcs.build_conversation_hints(int(self.agent_id), self, world, int(t))
        if hints:
            prefix.append(hints)

        if self.player_memory:
            # A8: skip stale-state force update_state while responding to player.
            saved_set_at = int(getattr(self, "current_state_set_at", 0) or 0)
            self.current_state_set_at = int(t)
            try:
                base = super()._observation_to_text(obs, t)
            finally:
                self.current_state_set_at = saved_set_at
            base = self._replace_demo_tail(base)
        else:
            base = super()._observation_to_text(obs, t)
            if (
                getattr(obs, "scripted_notification", None)
                or getattr(self, "_batch_turn_context", None)
            ):
                base = self._replace_demo_tail(base)

        if prefix:
            return "\n".join(prefix) + "\n\n" + base
        return base

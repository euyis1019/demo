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

STORY_ADVANCE_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "story_advance",
        "description": (
            "标记结构化剧情信号（不替你说台词）。"
            "Phase 1 节点 A：Jensen 发批准 RDC 给前台后调用 approve_visitor 进入 Phase 2。"
            "在已用 speak/RDC 完成对话后，当剧情应进入下一幕时调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "signal": {
                    "type": "string",
                    "enum": [
                        "approve_visitor",
                        "reject_visitor",
                        "return_to_negotiation",
                        "expel_ceos",
                        "offer_join",
                        "offer_seed",
                    ],
                    "description": "剧情推进信号",
                }
            },
            "required": ["signal"],
            "additionalProperties": False,
        },
    },
}

HBM_TOOLS: List[Dict[str, Any]] = list(DEMO_TOOLS) + [RELATION_CHANGE_TOOL, STORY_ADVANCE_TOOL]

_DEMO_TAIL_MARKER = "【本拍硬性要求】"

_HBM_TOOLS_LIST = (
    "  • speak_to_local           —— 当面说话（只对同地点的人有效）\n"
    "  • send_message             —— 私信某个 agent_id（1 拍后到达）\n"
    "  • send_to_group            —— 在群里说话（你必须是群成员）\n"
    "  • update_state             —— 改写自己的当前内心状态\n"
    "  • do_nothing               —— 真的无话可说时才用\n"
    "  • relation_change          —— 建立/断绝关系（仅剧情允许时）\n"
    "  • story_advance            —— 标记剧情节点信号（approve_visitor 等，不替你说台词）"
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
        from agent_world.hbm_demo.features.f15_prompt_trace.store import PromptTraceStore

        trace_store = PromptTraceStore(world_db) if world_db is not None else None
        if trace_store is not None and trace_store.enabled:
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

    def _hbm_short_action_rules(self) -> str:
        ctx = getattr(self, "_batch_turn_context", None) or {}
        phase = str(ctx.get("phase", ""))
        player_turn = int(ctx.get("player_turn", 0))
        aid = int(self.agent_id)

        reception_extra = ""
        if aid == 1 and phase == "Phase 1":
            reception_extra = (
                "3) 你在前台：每句玩家 inject 须 speak_to_local 回应；"
                "同批或下一拍须 send_message RDC→Jensen 简报（不可只 F2F）；"
                "收到 Jensen 批准 RDC 后 speak_to_local 请跟我来；"
                "Jensen「稍等/评估」RDC 只 speak_to_local 转告，勿 RDC→2。\n"
            )
        elif aid == 1:
            reception_extra = (
                "3) 你在前台：每句玩家 inject 须 speak_to_local 回应；"
                "有技术突破再 send_message RDC→Jensen；已汇报且老板未回时选 do_nothing。\n"
            )
        elif phase == "Phase 1" and aid == 2:
            reception_extra = (
                "3) 谈判室：speak_to_local 与 VP/CEO 谈 HBM；"
                "收到前台 RDC 后须 send_message→1 回执，再 send_message→3 求证；"
                "VP 回评估后 send_message→1 批准语（私人会议室/这边请），"
                "再 story_advance(approve_visitor) 进 Phase 2；勿复读「稍等」。\n"
            )
        elif phase == "Phase 1" and aid == 3:
            reception_extra = (
                "3) 谈判室：Jensen RDC 求证时须 send_message→2；"
                "其余 tick speak_to_local 插话或主动 RDC→2，保持与 Jensen 联动；"
                "禁止说「去私人会议室」。\n"
            )
        elif phase == "Phase 1" and aid in (4, 5, 6):
            reception_extra = (
                "3) 谈判室：speak_to_local 1–2 句与 Jensen/VP/其他 CEO 互怼 HBM 价格；"
                "勿联系玩家。\n"
            )
        elif phase == "Phase 2" and aid == 2:
            reception_extra = (
                "3) 私密审查：先 speak_to_local 回应玩家，再 RDC→Tech VP 或 update_state。\n"
            )
        elif phase == "Phase 2" and aid == 3:
            reception_extra = (
                "3) 仅回复 Jensen 未读 RDC：send_message→2，1–3 句；"
                "正面用「可行/核武器/理论上成立」。\n"
            )
        elif phase == "Phase 3" and aid in (2, 3):
            reception_extra = (
                "3) Phase 3 帮玩家圆场：引用玩家 inject 关键词，压 CEO 价，"
                "禁止帮 CEO 攻击玩家。\n"
            )
        elif phase == "Phase 3" and aid in (4, 5, 6):
            reception_extra = (
                "3) Phase 3 CEO 进攻：攻击玩家方案；可 GRP→200，"
                "禁止帮 NVIDIA 说话。\n"
            )
        elif phase == "Phase 3" and aid == 7 and player_turn >= 16:
            reception_extra = "3) Sam 搅局：仅 RDC，短句煽风，禁止 MOVE。\n"
        elif phase == "Phase 4" and aid == 2:
            reception_extra = (
                "3) 终局 1v1：先 speak_to_local 回应玩家，再 update_state 或短句 offer；"
                "一句一句来，禁止演讲开场。\n"
            )

        respond_rule = (
            "1) 有玩家 inject 时须首次回应其关键词；已回应且无新消息时选 do_nothing。\n"
        )
        from agent_world.hbm_demo.features.f07_agent_control.config import (
            is_experience_hardening,
        )

        if (
            is_experience_hardening()
            and phase == "Phase 1"
            and aid in (2, 3)
            and not self.player_memory
        ):
            respond_rule = (
                "1) 若本拍无新前台 RDC，选 do_nothing；"
                "勿主动发起与当前访客无关的话题。\n"
            )
        elif phase == "Phase 1" and aid in (2, 3) and not self.player_memory:
            respond_rule = (
                "1) 有未读 RDC 时本拍须 send_message 回复发件人（1–3 句），"
                "优先于 update_state / do_nothing。\n"
            )
            if aid == 2:
                respond_rule += (
                    "   前台 Agent1 首次 RDC 汇报后须 send_message→1 一句回执，"
                    "再 send_message→3 求证；勿复读私人会议室指令。\n"
                )
            else:
                respond_rule += (
                    "   Jensen RDC 求证时 send_message→2；否则 speak_to_local 或主动 RDC→2。\n"
                )
        elif phase == "Phase 2" and aid == 3:
            respond_rule = "1) 本拍仅回复 Jensen RDC，无需回应玩家（你看不到玩家原话）。\n"
        elif phase == "Phase 1" and aid == 1 and not self.player_memory:
            ctx = getattr(self, "_batch_turn_context", None) or {}
            if ctx.get("player_inject_tick") is None:
                respond_rule = (
                    "1) 玩家尚未发言——本拍 speak_to_local 一句欢迎即可；"
                    "禁止赶客、禁止 RDC。\n"
                )
            else:
                respond_rule = (
                    "1) 有未读 RDC 时本拍须 send_message 回复发件人；"
                    "无未读时 do_nothing。\n"
                )
        elif not self.player_memory and phase not in ("Phase 4",):
            respond_rule = (
                "1) 有未读 RDC 时本拍须 send_message 回复发件人；"
                "无未读时可 speak_to_local / update_state / do_nothing。\n"
            )

        length_rule = "2) 说出口的内容：短句口语（1–4 句），禁止演讲腔；上下文详 ≠ 长篇大论。\n"
        if phase == "Phase 3" and aid in (2, 3):
            length_rule = (
                "2) 说出口 2–5 句，可略长但必须引用玩家观点；禁止演讲腔。\n"
            )
        elif phase == "Phase 4" and aid == 2:
            length_rule = "2) 终局 1–3 句口语，一句一句回应玩家；禁止长篇独白。\n"

        return (
            "【本回合行动要求（HBM Demo · F07）】\n"
            f"{respond_rule}"
            f"{length_rule}"
            f"{reception_extra}"
            "4) 遵守系统约束中的阶段禁止项（MOVE/GRP 等）；request_move 被引擎忽略，"
            "台词里不要说「我去XX室」——位置不会变。\n"
            "5) 每一拍只调用一个工具，参数严格符合 schema。\n"
            "6) 无未读 RDC、无新 inject、且本批已说过话 → 可 do_nothing；有未读 RDC 时禁止 do_nothing。\n"
            "7) incoming_messages / 未读 RDC → 本拍必须 send_message 回复发件人，不要拖到下一拍。\n"
            "8) 他人给你 RDC 后你也应回复——全角色通用；同一指令勿连发多条相同 RDC。\n"
            "\n可选工具：\n"
            f"{_HBM_TOOLS_LIST}\n"
            "保持人物性格——输入上下文可长，实际发言必须短。"
        )

    def _replace_demo_tail(self, text: str) -> str:
        idx = text.find(_DEMO_TAIL_MARKER)
        head = text[:idx].rstrip() if idx >= 0 else text.rstrip()
        return head + "\n\n" + self._hbm_short_action_rules()

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
        ctx = getattr(self, "_batch_turn_context", None) or {}
        phase = str(ctx.get("phase", ""))
        if (
            int(self.agent_id) == 1
            and phase == "Phase 1"
            and not self.player_memory
            and ctx.get("player_inject_tick") is None
        ):
            from types import SimpleNamespace

            from agent_world.hbm_demo.features.f07_agent_control.knowledge import (
                build_agent_knowledge,
            )

            session = SimpleNamespace(
                phase=phase,
                player_turn=int(ctx.get("player_turn", 1)),
            )
            opening_block = build_agent_knowledge(
                session,
                int(self.agent_id),
                "",
                channel="opening",
            )
            if opening_block:
                prefix.append(opening_block)

        if world_db is not None:
            from agent_world.hbm_demo.features.f01_session.paths import get_name_map
            from agent_world.hbm_demo.features.f07_agent_control.knowledge import (
                build_thread_recap,
            )

            recap = build_thread_recap(
                int(self.agent_id),
                int(t),
                world_db,
                get_name_map(),
            )
            if recap:
                prefix.append(recap)

        from agent_world.hbm_demo.features.f07_agent_control.conversation_control import (
            build_conversation_hints,
        )

        hints = build_conversation_hints(int(self.agent_id), self, world, int(t))
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

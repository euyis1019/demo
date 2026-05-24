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

        user_text = self._observation_to_text(obs, t)
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_text},
        ]

        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=HBM_TOOLS,
                tool_choice="auto",
                temperature=float(
                    getattr(self, "_batch_temperature", None)
                    if getattr(self, "_batch_temperature", None) is not None
                    else self.temperature
                ),
                max_tokens=int(
                    getattr(self, "_batch_max_tokens", None)
                    if getattr(self, "_batch_max_tokens", None) is not None
                    else self.max_tokens
                ),
                **self.completion_extras,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("agent %s LLM call failed: %s", self.agent_id, exc)
            return _Response(info={"tool_calls": []})

        msg = resp.choices[0].message
        tool_calls: List[_ToolCall] = []
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

        turn_ctx = getattr(self, "_batch_turn_context", None)
        if turn_ctx:
            from agent_world.hbm_demo.features.f07_agent_control.tool_guard import (
                filter_tool_calls,
            )

            tool_calls = filter_tool_calls(
                self.agent_id,
                turn_ctx,
                tool_calls,
                batch_guard=getattr(self, "_batch_guard_state", None),
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
        if aid == 1:
            reception_extra = (
                "3) 你在前台：必须优先 speak_to_local 回应玩家，"
                "再 send_message RDC→Jensen。\n"
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

        respond_rule = "1) 必须先回应玩家注入记忆中的原话（复述或引用关键词）。\n"
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
        elif phase == "Phase 2" and aid == 3:
            respond_rule = "1) 本拍仅回复 Jensen RDC，无需回应玩家（你看不到玩家原话）。\n"
        elif not self.player_memory and phase == "Phase 3" and aid in (4, 5, 6):
            respond_rule = "1) 本拍根据谈判室局势发言，攻击玩家方案或密谋压价。\n"

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
            "4) 遵守系统约束中的阶段禁止项（MOVE/GRP 等）；违规将被引擎拒绝。\n"
            "5) 每一拍只调用一个工具，参数严格符合 schema。\n"
            "\n可选工具：\n"
            f"{_HBM_TOOLS_LIST}\n"
            "保持人物性格——输入上下文可长，实际发言必须短。"
        )

    def _replace_demo_tail(self, text: str) -> str:
        idx = text.find(_DEMO_TAIL_MARKER)
        head = text[:idx].rstrip() if idx >= 0 else text.rstrip()
        return head + "\n\n" + self._hbm_short_action_rules()

    def _observation_to_text(self, obs: Any, t: int) -> str:
        prefix: List[str] = []

        if self.player_memory:
            prefix.append("# 玩家/系统注入的对话记忆（必须认真回应）：")
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

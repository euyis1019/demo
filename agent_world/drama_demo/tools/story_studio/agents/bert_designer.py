"""Bert 设计师 管理 agent —— 取代 Designer（任务链）。

单一能力：把用户 brief + 已定的选角（cast）编译成一组 **bert**（「条件→反应」规则）：
玩家做某事(trigger) → 某 NPC(target) 产生某反应(reaction)；经 arms/requires 串成反应链；
ending 非空的 bert 即结局。不再有「幕/phase/节点/任务」。

★这是「教会管理 agent 如何设计 bert」——引擎不内嵌任何剧情硬规则，全部 bert 由本 agent 按剧情生成。
需要 cast（agent_id + 名字 + 地点）才能把 trigger/reaction 落到具体 NPC，故在选角之后运行。
LLM 客户端注入，离线可测；schema 校验/重试由 base_agent 负责，引用闭合/可达/结局由 BertSet.validate 兜。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from agent_world.drama_demo.tools.story_studio.authoring_schemas import BERT_OUTPUT_SCHEMA
from agent_world.drama_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

_SYSTEM = """你是互动剧的「反应设计师」。整部剧不靠分幕/任务推进，而靠一组 **bert**——
每条 bert 是一条「玩家做某事 → 某个 NPC 产生某个反应」的剧情规则。你要把 brief 拆成这样一组规则。

只输出 JSON：
{
  "berts": [
    {
      "id": "唯一id",
      "trigger": "玩家做/说了什么才触发——写成自然语言条件，运行期由导演读对话判断是否命中",
      "target": <这个反应是哪个 NPC 的，填他的 agent_id（见下方 cast）>,
      "reaction": "触发后该 NPC 要演的反应（一句话，演员据此演）",
      "place": "（可选）仅当玩家在此地点时才触发，填地点 id；不填=任何地点",
      "once": true,
      "arms": ["（可选）本条触发后才「上膛」的后续 bert id——用它串反应链"],
      "requires": ["（可选）需先触发过的前置 bert id；不填=开局就上膛"]
    },
    {
      "id": "结局id",
      "trigger": "走到这种收场的条件",
      "ending": {"kind": "good|neutral|bad", "summary": "一句话这种结局是怎样的"}
    }
  ]
}

★bert 怎么写（核心，看这个例子）：
  场景里有个罪犯不想被发现。设计成：
  - bert A：trigger=「玩家当面质问他是不是他干的、并施加压力」，target=该罪犯，
    reaction=「顶不住压力，向玩家坦白是自己干的」，arms=["B"]
  - bert B：trigger=「玩家答应替他求情/从轻」，requires=["A"]（A 触发后才上膛），
    target=该罪犯，reaction=「跪求宽大，交代出同伙」
  这就是一条**反应链**：固定的玩家行为触发特定 NPC 反应，一环扣一环。

★规则：
- trigger 要写**玩家的具体行为/话语**（"玩家逼问X""玩家拿出证据""玩家答应保护他"），
  不要写成 NPC 视角或抽象状态。
- target 必须是下方 cast 里真实存在的 agent_id。reaction 写成**该角色这一拍的「反应意图/态度转变」**
  （如"顶不住压力，决定向玩家坦白"、"嘴硬反咬一口、想把玩家唬住"），贴他的口吻与内心——
  **但不要写成让演员逐字照念的成品台词**：留给演员用自己的说话风格演出来，能用神态动作暗示就别直接写"他很紧张"。
- 用 requires/arms 把 bert 串成有因果的反应链（坦白→求情→交代…），别让它们各自孤立。
- **结局**：至少 1 条 ending 非空的 bert；故事抉择空间大就多给几个（good/neutral/bad 自由搭，不必凑齐）。
  结局 bert 不需要 target/reaction，只要 trigger + ending。
- **bert 数量由剧情自然决定**（简单冲突 3-5 条，丰满的 8-15 条都行），环环相扣、不注水。
- 每条非结局 bert 都必须能从「开局就上膛的 bert」经 arms 链到达，别留永不触发的孤儿。
不要输出人物设定、地点定义、对白脚本——只要这组 bert 规则。"""


def _cast_digest(cast: Dict[str, Any]) -> str:
    """从 Casting 产物摘出 bert 设计师需要的角色信息：人设/口吻/内心/处境——
    reaction 要贴该角色的口吻与处境来写，信息不全就只能写成通用 AI 腔，与演员学到的口吻打架。"""
    lines: List[str] = [
        "可用角色（target 只能填这些 agent_id；写 reaction 时务必用该角色「口吻」栏的语气、贴他的内心与处境）："
    ]
    for a in cast.get("agents") or []:
        if int(a.get("agent_id", -1)) == 0:
            continue  # 玩家(agent 0)不作为 reaction 的 target
        bits = [f"  agent_id={a.get('agent_id')}：{a.get('name','?')}（{a.get('role','')}）"]
        if a.get("soul"):
            bits.append(f"\n    人设：{a['soul']}")
        if a.get("speech_style"):
            bits.append(f"\n    口吻：{a['speech_style']}")
        if a.get("inner"):
            bits.append(f"\n    内心图谋/秘密：{a['inner']}")
        if a.get("current_state"):
            bits.append(f"\n    开局处境：{a['current_state']}")
        lines.append("".join(bits))
    places = [p.get("id") or p.get("place_id") for p in (cast.get("places") or [])]
    places = [p for p in places if p]
    if places:
        lines.append("可用地点 id（place 只能填这些）：" + "、".join(map(str, places)))
    return "\n".join(lines)


def _build_user_prompt(brief: Dict[str, Any], cast: Dict[str, Any]) -> str:
    return (
        "故事 brief（YAML/JSON）：\n"
        + json.dumps(brief, ensure_ascii=False, indent=2)
        + "\n\n"
        + _cast_digest(cast)
    )


class BertDesigner:
    """brief + cast → BertOutput（berts，含结局 bert）。"""

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def run(self, brief: Dict[str, Any], cast: Dict[str, Any], *, feedback: str = "") -> Dict[str, Any]:
        user = _build_user_prompt(brief, cast)
        if feedback:
            user += f"\n\n[上一版校验未过，请修正后重新输出完整 JSON]\n{feedback}"
        return call_json_with_schema(
            self._client,
            system=_SYSTEM,
            user=user,
            schema=BERT_OUTPUT_SCHEMA,
            label="bert_designer",
        )

"""F04 LLM scoring for player turn Stats deltas（数据驱动，无写死故事维度）。

维度集与裁判人设来自活跃 Story Pack 的 meta.stats（管理 agent 生成）；本模块据此泛化打分，
返回 {dim_key: delta}。无 meta.stats 时返回空（该故事不启用属性面板）。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from openai import OpenAI

from agent_world.drama_demo.features.f01_session.models import DramaSession
from agent_world.drama_demo.features.f01_session.paths import get_scenario
from agent_world.drama_demo.core.runner.kernel import llm_request_extras, resolve_api_key

log = logging.getLogger("agent_world.drama_demo.game_service")


def _llm_client() -> OpenAI:
    llm_cfg = get_scenario().get("llm", {}) or {}
    return OpenAI(
        api_key=resolve_api_key(llm_cfg),
        base_url=llm_cfg.get("base_url", "https://api.deepseek.com"),
    )


def _parse_stats_json(text: str, keys: List[str]) -> Dict[str, int]:
    raw = text.strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        raw = match.group(0)
    data = json.loads(raw)
    out: Dict[str, int] = {}
    for k in keys:
        try:
            out[k] = int(data.get(f"{k}_delta", 0) or 0)
        except (TypeError, ValueError):
            out[k] = 0
    return out


def _heuristic_stats(player_text: str, keys: List[str]) -> Dict[str, int]:
    """LLM 失败时的中性兜底：发言有实质内容则各维度微涨，过短则不动（无任何故事关键词）。"""
    text = " ".join(str(player_text or "").split())
    bump = 1 if len(text) >= 8 else 0
    return {k: bump for k in keys}


def score_player_turn(session: DramaSession, player_text: str) -> Dict[str, int]:
    """返回各维度增量 {key: delta}。维度由活跃 Story Pack 的 meta.stats 决定；无维度则返回 {}。"""
    from agent_world.drama_demo.shared import story_config

    design: Dict[str, Any] = story_config.stats_design()
    dims = design.get("dimensions") or []
    keys = [str(d["key"]) for d in dims if d.get("key")]
    if not keys:
        return {}

    llm_cfg = get_scenario().get("llm", {}) or {}
    model = llm_cfg.get("model", "deepseek-chat")
    persona = str(design.get("judge_persona") or "你是这部互动剧情的裁判。")
    dim_lines = "\n".join(
        f"- {d['key']}（{d.get('label', d['key'])}）：{d.get('description', '')}" for d in dims
    )
    system = (
        f"{persona}\n根据玩家本回合发言，评估其在以下维度的增量（每个 -5~+5 的整数），"
        "只输出 JSON，字段为 " + ", ".join(f"{k}_delta" for k in keys) + " 以及可选 reason。\n"
        f"维度说明：\n{dim_lines}"
    )
    user = json.dumps(
        {"player_text": player_text, "stats": session.stats, "player_turn": session.player_turn},
        ensure_ascii=False,
    )
    try:
        resp = _llm_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
            max_tokens=200,
            **llm_request_extras(llm_cfg),
        )
        content = (resp.choices[0].message.content or "").strip()
        return _parse_stats_json(content, keys)
    except Exception as exc:  # noqa: BLE001
        log.warning("score_player_turn LLM failed, using heuristic: %s", exc)
        return _heuristic_stats(player_text, keys)

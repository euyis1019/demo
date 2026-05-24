"""F04 LLM scoring and immediate scene reaction."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import re
from typing import Dict

from openai import OpenAI

from agent_world.hbm_demo.features.f01_session.models import HbmSession
from agent_world.hbm_demo.features.f01_session.paths import get_scenario
from agent_world.hbm_demo.core.runner.kernel import llm_request_extras, resolve_api_key
from agent_world.hbm_demo.shared.settings import IMMEDIATE_MSG_TIMEOUT

log = logging.getLogger("agent_world.hbm_demo.game_service")

IMMEDIATE_MSG_PLACEHOLDER = "前台接待员听完你的话，若有所思…"


def _llm_client() -> OpenAI:
    llm_cfg = get_scenario().get("llm", {}) or {}
    return OpenAI(
        api_key=resolve_api_key(llm_cfg),
        base_url=llm_cfg.get("base_url", "https://api.deepseek.com"),
    )


def _parse_stats_json(text: str) -> Dict[str, int]:
    raw = text.strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        raw = match.group(0)
    data = json.loads(raw)
    return {
        "vision_delta": int(data.get("vision_delta", 0) or 0),
        "execution_delta": int(data.get("execution_delta", 0) or 0),
        "trust_delta": int(data.get("trust_delta", 0) or 0),
        "burnout_delta": int(data.get("burnout_delta", 0) or 0),
    }


def _heuristic_stats(session: HbmSession, player_text: str) -> Dict[str, int]:
    text = player_text.lower()
    tech_kw = ("显存", "算法", "80%", "内存", "优化", "架构", "降低")
    if any(k in player_text for k in tech_kw):
        return {
            "vision_delta": 5,
            "execution_delta": 4,
            "trust_delta": 1,
            "burnout_delta": 0,
        }
    if len(text) < 8:
        return {
            "vision_delta": 0,
            "execution_delta": 0,
            "trust_delta": 0,
            "burnout_delta": 1,
        }
    return {
        "vision_delta": 1,
        "execution_delta": 1,
        "trust_delta": 0,
        "burnout_delta": 0,
    }


def score_player_turn(session: HbmSession, player_text: str) -> Dict[str, int]:
    llm_cfg = get_scenario().get("llm", {}) or {}
    model = llm_cfg.get("model", "deepseek-v4-flash")
    system = (
        "你是《HBM 显存价格保卫战》的游戏裁判。"
        "根据玩家本回合发言与当前 Phase，输出四维属性增量 JSON。"
        "只输出 JSON，字段：vision_delta, execution_delta, trust_delta, "
        "burnout_delta, reason。"
    )
    user = json.dumps(
        {
            "player_text": player_text,
            "phase": session.phase,
            "player_turn": session.player_turn,
            "stats": session.stats,
        },
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
        return _parse_stats_json(content)
    except Exception as exc:  # noqa: BLE001
        log.warning("score_player_turn LLM failed, using heuristic: %s", exc)
        return _heuristic_stats(session, player_text)


def _call_immediate_llm(session: HbmSession, player_text: str) -> str:
    llm_cfg = get_scenario().get("llm", {}) or {}
    model = llm_cfg.get("model", "deepseek-v4-flash")
    resp = _llm_client().chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "用一句中文描写 NPC 听完玩家发言后的即时反应，20字以内。",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "phase": session.phase,
                        "place_id": session.place_id,
                        "player_text": player_text,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        temperature=0.8,
        max_tokens=60,
        **llm_request_extras(llm_cfg),
    )
    text = (resp.choices[0].message.content or "").strip()
    return text or IMMEDIATE_MSG_PLACEHOLDER


def generate_immediate_msg(
    session: HbmSession,
    player_text: str,
    *,
    timeout: float = IMMEDIATE_MSG_TIMEOUT,
) -> str:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_call_immediate_llm, session, player_text)
            return fut.result(timeout=timeout)
    except Exception:  # noqa: BLE001
        return IMMEDIATE_MSG_PLACEHOLDER

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

IMMEDIATE_MSG_PLACEHOLDER = "Morgen 在小本本上写下一行，猫假装没看见…"


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
    avoid_kw = ("不去", "借口", "拉黑", "已读不回", "不喝", "透明", "洗头", "空手")
    bold_kw = ("打电话", "会发", "喝", "直接", "重测", "反抗", "五块", "5块")
    mbti_kw = ("mbti", "sbti", "社恐", "i人", "测试", "在吗", "团建")
    if any(k in player_text or k in text for k in avoid_kw):
        return {
            "vision_delta": 2,
            "execution_delta": 5,
            "trust_delta": 1,
            "burnout_delta": 2,
        }
    if any(k in player_text or k in text for k in bold_kw):
        return {
            "vision_delta": 4,
            "execution_delta": 2,
            "trust_delta": 2,
            "burnout_delta": 4,
        }
    if any(k in player_text or k in text for k in mbti_kw):
        return {
            "vision_delta": 3,
            "execution_delta": 2,
            "trust_delta": 1,
            "burnout_delta": 1,
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
    model = llm_cfg.get("model", "deepseek-chat")
    system = (
        "你是《暗黑心理诊所》的游戏裁判。"
        "根据玩家本回合发言与当前 Phase，输出四维属性增量 JSON。"
        "四维含义：vision_delta=脑洞值，execution_delta=逃避值，trust_delta=记忆锚点，burnout_delta=社死压力。"
        "逃避、沉默、拉黑、洗头借口提高逃避值；主动社死、打电话、反抗诊断提高脑洞和社死压力。"
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
    model = llm_cfg.get("model", "deepseek-chat")
    resp = _llm_client().chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "用一句中文描写暗黑心理诊所 NPC 听完玩家发言后的即时反应，20字以内，黑色幽默。",
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

"""PlayerAgent 测试：命令校验白名单 + 队列驱动的动作产出。"""

from __future__ import annotations

import pytest

from cyber_town.backend.player_agent import PlayerAgent


def _agent() -> PlayerAgent:
    return PlayerAgent(agent_id=0, name="农场主")


def test_push_rejects_unknown_action() -> None:
    assert _agent().push_command({"action": "hack_world", "kwargs": {}}) is False


def test_push_rejects_missing_kwargs() -> None:
    a = _agent()
    assert a.push_command({"action": "send_message", "kwargs": {"content": "hi"}}) is False
    assert a.push_command({"action": "request_move", "kwargs": {}}) is False


def test_push_accepts_valid_commands() -> None:
    a = _agent()
    assert a.push_command({"action": "speak_to_local", "kwargs": {"content": "早"}})
    assert a.push_command(
        {"action": "send_message", "kwargs": {"target": 1, "content": "嗨"}}
    )
    assert a.command_queue.qsize() == 2


@pytest.mark.asyncio
async def test_perform_action_pops_one_command_per_tick() -> None:
    a = _agent()
    a.push_command({"action": "speak_to_local", "kwargs": {"content": "第一句"}})
    a.push_command({"action": "request_move", "kwargs": {"place_id": "square"}})

    r1 = await a.perform_action_by_llm(world=None, t=0)
    calls1 = r1.info["tool_calls"]
    assert len(calls1) == 1 and calls1[0].tool_name == "speak_to_local"
    assert calls1[0].args == {"content": "第一句"}

    r2 = await a.perform_action_by_llm(world=None, t=1)
    assert r2.info["tool_calls"][0].tool_name == "request_move"


@pytest.mark.asyncio
async def test_empty_queue_yields_do_nothing() -> None:
    r = await _agent().perform_action_by_llm(world=None, t=0)
    assert r.info["tool_calls"][0].tool_name == "do_nothing"

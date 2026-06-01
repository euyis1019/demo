"""F15 Flask handlers — prompt trace lookup."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_world.drama_demo.features.f06_read_model.world_db import make_readonly_db
from agent_world.drama_demo.shared.errors import RunnerNotReadyError
from agent_world.drama_demo.shared.env_status import is_runner_ready


def _parse_tool_calls(raw: Optional[str]) -> List[Dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return data if isinstance(data, list) else []


def _serialize_trace(row: Dict[str, Any], links: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "trace_id": row["trace_id"],
        "agent_id": int(row["agent_id"]),
        "at_tick": int(row["at_tick"]),
        "phase": row.get("phase"),
        "player_turn": (
            None if row.get("player_turn") is None else int(row["player_turn"])
        ),
        "model": row.get("model"),
        "temperature": row.get("temperature"),
        "max_tokens": row.get("max_tokens"),
        "system_prompt": row.get("system_prompt") or "",
        "user_prompt": row.get("user_prompt") or "",
        "tool_calls": _parse_tool_calls(row.get("tool_calls_json")),
        "assistant_content": row.get("assistant_content"),
        "created_at": row.get("created_at"),
        "links": [
            {
                "link_kind": link["link_kind"],
                "ref_key": link["ref_key"],
                "agent_id": int(link["agent_id"]),
                "at_tick": int(link["at_tick"]),
            }
            for link in links
        ],
    }


def get_prompt_trace(
    *,
    sim_dir: Path,
    trace_id: str,
) -> Dict[str, Any]:
    if not is_runner_ready(sim_dir):
        raise RunnerNotReadyError("Runner not ready")

    db = make_readonly_db(sim_dir)
    row = db.fetch_trace_by_id(str(trace_id))
    if row is None:
        raise KeyError(f"trace not found: {trace_id}")
    links = db.fetch_trace_links_for_trace(str(trace_id))
    return _serialize_trace(row, links)


def get_prompt_trace_by_ref(
    *,
    sim_dir: Path,
    ref_key: str,
) -> Dict[str, Any]:
    if not is_runner_ready(sim_dir):
        raise RunnerNotReadyError("Runner not ready")

    db = make_readonly_db(sim_dir)
    trace_id = db.fetch_trace_id_by_ref_key(str(ref_key))
    if not trace_id:
        raise KeyError(f"no trace for ref_key: {ref_key}")
    row = db.fetch_trace_by_id(trace_id)
    if row is None:
        raise KeyError(f"trace not found: {trace_id}")
    links = db.fetch_trace_links_for_trace(trace_id)
    return _serialize_trace(row, links)


def list_prompt_traces(
    *,
    sim_dir: Path,
    agent_id: Optional[int] = None,
    since_tick: Optional[int] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    if not is_runner_ready(sim_dir):
        raise RunnerNotReadyError("Runner not ready")

    db = make_readonly_db(sim_dir)
    return db.list_traces(
        agent_id=agent_id,
        since_tick=since_tick,
        limit=min(max(int(limit), 1), 200),
    )


__all__ = ["get_prompt_trace", "get_prompt_trace_by_ref", "list_prompt_traces"]

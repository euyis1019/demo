"""F07-E6 — Phase 4 IPC smoke (dev_logs/29 §3.6.4, §10.6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

from agent_world.hbm_demo.features.f05_story_routing.routing import (
    PLACE_NEGOTIATION,
    build_inject_payload,
)
from agent_world.hbm_demo.features.f06_read_model.world_db import ReadOnlyWorldDB
from agent_world.hbm_demo.features.f07_agent_control.config import (
    is_f07_enabled,
    resolve_inject_tick_count,
)
from agent_world.hbm_demo.http.ipc_helper import (
    get_ipc_client,
    send_inject_batch,
    send_move_agent,
    send_reset_world,
)
from agent_world.ipc.commands import CommandType


@dataclass
class Phase4SmokeResult:
    inject_agent_ids: List[int]
    start_tick: int
    end_tick: int
    jensen_f2f_count: int
    vp_public_count: int
    ceo_in_negotiation: List[int]
    agent_locations: Dict[str, str]

    @property
    def ok(self) -> bool:
        if self.inject_agent_ids != [2]:
            return False
        if self.jensen_f2f_count < 1:
            return False
        if self.vp_public_count != 0:
            return False
        if self.ceo_in_negotiation:
            return False
        return True


def run_phase4_ipc_smoke(
    sim_dir: str | Path,
    *,
    player_text: str = "我接受加入团队，但我们先谈股权结构和期权池。",
    ipc_timeout: float = 120.0,
) -> Phase4SmokeResult:
    """Reset world, MOVE CEOs out, inject Phase 4 Turn 21, read negotiation_room F2F."""
    sim_path = Path(sim_dir).resolve()
    client = get_ipc_client(str(sim_path))

    send_reset_world(client, timeout=ipc_timeout)

    for aid in (4, 5, 6):
        send_move_agent(
            client,
            agent_id=aid,
            place_id="nvidia_reception",
            timeout=ipc_timeout,
        )

    session = SimpleNamespace(
        phase="Phase 4",
        player_turn=21,
        place_id=PLACE_NEGOTIATION,
        stats={"vision": 32, "execution": 28, "trust": 18, "burnout": 15},
    )
    events, _broadcast, turn_context = build_inject_payload(
        session,
        player_text,
        task_id="f07_e6_phase4_smoke",
    )
    inject_ids = [
        int(ev["effect"]["agent_id"])
        for ev in events
        if (ev.get("effect") or {}).get("type") == "dialogue_injection"
    ]

    tick_count = resolve_inject_tick_count("Phase 4", 12) if is_f07_enabled() else 8
    inject_resp = send_inject_batch(
        client,
        events=events,
        tick_count=tick_count,
        turn_context=turn_context,
        timeout=ipc_timeout,
    )
    result = inject_resp.result or {}
    start_tick = int(result.get("start_tick", 0))
    end_tick = int(result.get("end_tick", start_tick))

    list_resp = client.send_command(CommandType.LIST_PLACES, {}, timeout=ipc_timeout)
    locations_raw = (list_resp.result or {}).get("agent_locations") or {}
    agent_locations = {str(k): str(v) for k, v in locations_raw.items()}

    db_path = sim_path / "world.db"
    ro = ReadOnlyWorldDB(db_path)
    f2f_rows = ro.fetch_f2f_history_at(PLACE_NEGOTIATION, end_tick, start_tick)
    jensen_f2f = [row for row in f2f_rows if int(row[1]) == 2]
    vp_f2f = [row for row in f2f_rows if int(row[1]) == 3]

    ceo_in_negotiation = [
        aid
        for aid in (4, 5, 6)
        if agent_locations.get(str(aid)) == PLACE_NEGOTIATION
    ]

    return Phase4SmokeResult(
        inject_agent_ids=inject_ids,
        start_tick=start_tick,
        end_tick=end_tick,
        jensen_f2f_count=len(jensen_f2f),
        vp_public_count=len(vp_f2f),
        ceo_in_negotiation=ceo_in_negotiation,
        agent_locations=agent_locations,
    )


__all__ = ["Phase4SmokeResult", "run_phase4_ipc_smoke"]

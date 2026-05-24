"""F03 action completion rules and message formatting."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from agent_world.hbm_demo.features.f01_session.constants import DEFAULT_PHASE
from agent_world.hbm_demo.features.f07_agent_control.config import (
    is_experience_hardening,
    is_f07_enabled,
)
from agent_world.hbm_demo.features.f02_player_turn.task import (
    INJECT_STATUS_DONE,
    INJECT_STATUS_FAILED,
    INJECT_STATUS_PENDING,
    INJECT_STATUS_RUNNING,
    PendingTask,
)
from agent_world.hbm_demo.features.f06_read_model.world_db import (
    ReadOnlyWorldDB,
    sender_display_name,
)

PHASE_RDC_PAIRS: Dict[str, List[Tuple[int, int]]] = {
    "Phase 1": [(1, 2)],
    "Phase 2": [(2, 3), (3, 2)],
    "Phase 3": [
        (2, 3), (3, 2),
        (4, 2), (5, 2), (6, 2),
        (4, 5), (4, 6), (5, 6),
        (7, 2),
    ],
    "Phase 4": [(2, 3), (3, 2)],
}


def _rdc_pairs_for_phase(phase: str) -> List[Tuple[int, int]]:
    return list(PHASE_RDC_PAIRS.get(phase, PHASE_RDC_PAIRS[DEFAULT_PHASE]))


def _inject_finished(task: PendingTask) -> bool:
    if task.inject_status == INJECT_STATUS_DONE:
        return True
    # Legacy sync path: task saved with ipc_end_tick after inline inject.
    if task.inject_status == INJECT_STATUS_PENDING and task.ipc_end_tick is not None:
        return True
    return False


RECEPTION_PLACE = "nvidia_reception"
JENSEN_PRIVATE_PLACE = "jensen_private_room"
NEGOTIATION_PLACE = "negotiation_room"


def _f2f_required_completion(
    task: PendingTask,
    current_tick: int,
    db: ReadOnlyWorldDB,
    *,
    place_id: str,
) -> bool:
    """E5 — experience hardening: complete only on F2F (no pure timeout)."""
    start = task.start_tick
    if current_tick < start + 3:
        return False
    if db.has_f2f_after(place_id, start, current_tick):
        return True
    if task.inject_status == INJECT_STATUS_FAILED:
        return True
    return False


def check_action_complete(
    task: PendingTask,
    current_tick: int,
    db: ReadOnlyWorldDB,
) -> bool:
    start = task.start_tick
    if current_tick < start + 3:
        return False

    # E5 — F07-E: Phase 1/2/4 must have player-visible F2F; no timeout-only completion.
    if is_experience_hardening() and task.phase == "Phase 1":
        return _f2f_required_completion(
            task, current_tick, db, place_id=RECEPTION_PLACE
        )
    if is_experience_hardening() and task.phase == "Phase 2":
        place = task.place_id or JENSEN_PRIVATE_PLACE
        return _f2f_required_completion(task, current_tick, db, place_id=place)
    if is_experience_hardening() and task.phase == "Phase 4":
        place = task.place_id or NEGOTIATION_PLACE
        return _f2f_required_completion(task, current_tick, db, place_id=place)

    # §13.2 — Phase 1: only reception F2F (not RDC/GRP) completes early when F07 on.
    if is_f07_enabled() and task.phase == "Phase 1":
        if db.has_f2f_after(RECEPTION_PLACE, start, current_tick):
            return True
        if task.inject_status == INJECT_STATUS_FAILED:
            return True
        if not _inject_finished(task):
            return current_tick >= start + 8
        return current_tick >= start + 8

    # §13.5 — Phase 4: only negotiation_room F2F (Jensen↔玩家); not VP RDC/GRP.
    if is_f07_enabled() and task.phase == "Phase 4":
        place = task.place_id or NEGOTIATION_PLACE
        if db.has_f2f_after(place, start, current_tick):
            return True
        if task.inject_status == INJECT_STATUS_FAILED:
            return True
        if not _inject_finished(task):
            return current_tick >= start + 8
        if task.ipc_end_tick is not None and current_tick >= task.ipc_end_tick:
            return True
        return current_tick >= start + 8

    if db.has_f2f_after(task.place_id, start, current_tick):
        return True
    if db.has_rdc_pair_after(
        _rdc_pairs_for_phase(task.phase), start, current_tick
    ):
        return True
    if db.has_grp_after({100, 200}, start, current_tick):
        return True

    if task.inject_status == INJECT_STATUS_FAILED:
        return True

    if not _inject_finished(task):
        if current_tick >= start + 8:
            return True
        return False

    # Inject batch finished — world tick won't advance until the next player-turn.
    if task.ipc_end_tick is not None and current_tick >= task.ipc_end_tick:
        return True

    if current_tick >= start + 8:
        return True
    return False


def effective_tick_for_task(task: PendingTask, env_tick: int) -> int:
    if task.ipc_end_tick is not None:
        return max(env_tick, task.ipc_end_tick)
    return env_tick


def format_messages(
    rows: List[Any],
    name_map: Dict[int, str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        ch = str(row["channel_type"])
        item: Dict[str, Any] = {
            "sender": sender_display_name(row["sender_id"], name_map),
            "content": str(row["content"] or ""),
            "type": ch,
            "attempted_at": int(row["attempted_at"]),
        }
        if ch == "RDC":
            item["recipient"] = sender_display_name(row["recipient_id"], name_map)
        if ch == "GRP" and row["group_id"] is not None:
            item["group_id"] = int(row["group_id"])
        if row["place_id"]:
            item["place_id"] = str(row["place_id"])
        out.append(item)
    return out


def format_f2f_public_messages(
    history: List[Tuple[int, int, int, str]],
    name_map: Dict[int, str],
) -> List[Dict[str, Any]]:
    return [
        {
            "sender": sender_display_name(sender_id, name_map),
            "content": content,
            "type": "F2F",
            "attempted_at": at_t,
        }
        for at_t, sender_id, _mid, content in history
        if at_t > 0
    ]

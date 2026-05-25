"""F03 action completion rules and message formatting.

v2 Phase 0 (dev_logs/31): continuous delta read model — polling uses ``since_tick``
for incremental UI; ``check_action_complete`` no longer treats ``ipc_end_tick`` alone
as batch-completed when experience hardening is off.
"""

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

MIN_ACTIVITY_TICKS = 3
DEFAULT_TIMEOUT_TICKS = 8


def _rdc_pairs_for_phase(phase: str) -> List[Tuple[int, int]]:
    return list(PHASE_RDC_PAIRS.get(phase, PHASE_RDC_PAIRS[DEFAULT_PHASE]))


def _inject_finished(task: PendingTask) -> bool:
    if task.inject_status == INJECT_STATUS_DONE:
        return True
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
    if current_tick < start + MIN_ACTIVITY_TICKS:
        return False
    if db.has_f2f_after(place_id, start, current_tick):
        return True
    if task.inject_status == INJECT_STATUS_FAILED:
        return True
    return False


def _timeout_complete(task: PendingTask, current_tick: int) -> bool:
    return current_tick >= task.start_tick + DEFAULT_TIMEOUT_TICKS


def _f07_phase1_complete(
    task: PendingTask,
    start: int,
    current_tick: int,
    db: ReadOnlyWorldDB,
) -> bool:
    """§13.2 — Phase 1 completes on reception F2F or timeout; not RDC-only."""
    if db.has_f2f_after(RECEPTION_PLACE, start, current_tick):
        return True
    return _timeout_complete(task, current_tick)


def _f07_phase4_complete(
    task: PendingTask,
    start: int,
    current_tick: int,
    db: ReadOnlyWorldDB,
) -> bool:
    """§13.5 — Phase 4 completes on negotiation F2F or timeout; not VP RDC-only."""
    place = task.place_id or NEGOTIATION_PLACE
    if db.has_f2f_after(place, start, current_tick):
        return True
    return _timeout_complete(task, current_tick)


def check_action_complete(
    task: PendingTask,
    current_tick: int,
    db: ReadOnlyWorldDB,
) -> bool:
    """Return True when the client may stop polling for this turn."""
    start = task.start_tick
    if current_tick < start + MIN_ACTIVITY_TICKS:
        return False

    if task.inject_status == INJECT_STATUS_FAILED:
        return True

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

    if is_f07_enabled() and task.phase == "Phase 1":
        return _f07_phase1_complete(task, start, current_tick, db)

    if is_f07_enabled() and task.phase == "Phase 4":
        return _f07_phase4_complete(task, start, current_tick, db)

    if db.has_f2f_after(task.place_id, start, current_tick):
        return True
    if db.has_rdc_pair_after(
        _rdc_pairs_for_phase(task.phase), start, current_tick
    ):
        return True
    if db.has_grp_after({100, 200}, start, current_tick):
        return True

    if not _inject_finished(task):
        return _timeout_complete(task, current_tick)

    if is_experience_hardening():
        if task.ipc_end_tick is not None and current_tick >= task.ipc_end_tick:
            return True

    return _timeout_complete(task, current_tick)


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
        if row["sender_id"] is not None:
            item["sender_id"] = int(row["sender_id"])
        if ch == "RDC":
            item["recipient"] = sender_display_name(row["recipient_id"], name_map)
            item["recipient_id"] = int(row["recipient_id"])
        if ch == "GRP" and row["group_id"] is not None:
            item["group_id"] = int(row["group_id"])
        if row["place_id"]:
            item["place_id"] = str(row["place_id"])
        if "delivered" in row.keys():
            item["delivered"] = int(row["delivered"])
        if row["sender_id"] is not None and int(row["sender_id"]) == -1:
            item["is_system"] = True
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
            "sender_id": int(sender_id),
        }
        for at_t, sender_id, _mid, content in history
        if at_t > 0
    ]

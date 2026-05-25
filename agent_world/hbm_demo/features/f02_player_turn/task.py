"""F02 pending task model and Flask session persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f01_session.constants import DEFAULT_SIM_ID, TASKS_KEY

INJECT_STATUS_PENDING = "pending"
INJECT_STATUS_RUNNING = "running"
INJECT_STATUS_DONE = "done"
INJECT_STATUS_FAILED = "failed"


@dataclass
class PendingTask:
    task_id: str
    start_tick: int
    place_id: str
    phase: str
    player_turn: int
    ipc_end_tick: Optional[int] = None
    inject_status: str = INJECT_STATUS_PENDING
    inject_error: Optional[str] = None
    routing_info: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "task_id": self.task_id,
            "start_tick": self.start_tick,
            "place_id": self.place_id,
            "phase": self.phase,
            "player_turn": self.player_turn,
            "inject_status": self.inject_status,
        }
        if self.ipc_end_tick is not None:
            out["ipc_end_tick"] = self.ipc_end_tick
        if self.inject_error is not None:
            out["inject_error"] = self.inject_error
        if self.routing_info is not None:
            out["routing_info"] = dict(self.routing_info)
        return out

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PendingTask":
        ipc_end = data.get("ipc_end_tick")
        routing_raw = data.get("routing_info")
        return cls(
            task_id=str(data["task_id"]),
            start_tick=int(data["start_tick"]),
            place_id=str(data["place_id"]),
            phase=str(data["phase"]),
            player_turn=int(data["player_turn"]),
            ipc_end_tick=int(ipc_end) if ipc_end is not None else None,
            inject_status=str(data.get("inject_status") or INJECT_STATUS_PENDING),
            inject_error=data.get("inject_error"),
            routing_info=dict(routing_raw) if isinstance(routing_raw, dict) else None,
        )


def save_task(
    flask_session: Any,
    task: PendingTask,
    sim_id: str = DEFAULT_SIM_ID,
) -> None:
    store = flask_session.setdefault(TASKS_KEY, {})
    sim_tasks = store.setdefault(sim_id, {})
    sim_tasks[task.task_id] = task.to_dict()
    sim_tasks["__latest__"] = task.task_id
    flask_session.modified = True


def load_task(
    flask_session: Any,
    task_id: str,
    sim_id: str = DEFAULT_SIM_ID,
) -> Optional[PendingTask]:
    store = flask_session.get(TASKS_KEY) or {}
    raw = (store.get(sim_id) or {}).get(task_id)
    if not raw:
        return None
    return PendingTask.from_dict(raw)

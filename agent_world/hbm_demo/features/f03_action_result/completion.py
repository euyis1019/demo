"""F03 action completion rules（数据驱动，无写死故事 phase/agent/place/group）。

continuous delta read model：完成判定 = 玩家所在地点出现对白（NPC 已响应）或超时兜底，
据此让前端停止本回合轮询。旧版按写死的 HBM 幕名/角色编号/地点/群 id 判定的逻辑已退役。
"""

from __future__ import annotations

from agent_world.hbm_demo.features.f02_player_turn.task import (
    INJECT_STATUS_DONE,
    INJECT_STATUS_FAILED,
    INJECT_STATUS_PENDING,
    PendingTask,
)
from agent_world.hbm_demo.features.f06_read_model.world_db import ReadOnlyWorldDB

MIN_ACTIVITY_TICKS = 3
DEFAULT_TIMEOUT_TICKS = 8


def _inject_finished(task: PendingTask) -> bool:
    if task.inject_status == INJECT_STATUS_DONE:
        return True
    if task.inject_status == INJECT_STATUS_PENDING and task.ipc_end_tick is not None:
        return True
    return False


def _timeout_complete(task: PendingTask, current_tick: int) -> bool:
    return current_tick >= task.start_tick + DEFAULT_TIMEOUT_TICKS


def check_action_complete(
    task: PendingTask,
    current_tick: int,
    db: ReadOnlyWorldDB,
) -> bool:
    """Return True when the client may stop polling for this turn（通用：有对白 或 超时）。"""
    start = task.start_tick
    if current_tick < start + MIN_ACTIVITY_TICKS:
        return False

    if task.inject_status == INJECT_STATUS_FAILED:
        return True

    # 玩家所在地点出现任何当面对白 → 本回合已有响应，可停止轮询（不再按写死幕名/角色判定）。
    if db.has_f2f_after(task.place_id, start, current_tick):
        return True

    return _timeout_complete(task, current_tick)


def effective_tick_for_task(task: PendingTask, env_tick: int) -> int:
    if task.ipc_end_tick is not None:
        return max(env_tick, task.ipc_end_tick)
    return env_tick


from agent_world.hbm_demo.shared.messages import (  # noqa: E402
    format_f2f_public_messages,
    format_messages,
)

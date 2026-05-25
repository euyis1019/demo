"""Compatibility shim — game logic split into features/f01–f04, f06 (M2)."""

from agent_world.hbm_demo.features.f01_session.constants import (
    DEFAULT_CONFIG,
    DEFAULT_PHASE,
    DEFAULT_PLACE_ID,
    DEFAULT_SIM_ID,
    INITIAL_STATS,
    SESSION_KEY,
    TASKS_KEY,
)
from agent_world.hbm_demo.features.f01_session.lifecycle import (
    create_session,
    get_or_create_session,
    get_session_snapshot,
    load_session,
    save_session,
)
from agent_world.hbm_demo.features.f01_session.logging import log_turn_event
from agent_world.hbm_demo.features.f01_session.models import HbmSession
from agent_world.hbm_demo.features.f01_session.paths import (
    get_name_map,
    get_scenario,
    get_sim_dir,
    get_world_db_path,
)
from agent_world.hbm_demo.features.f01_session.reset import reset_demo
from agent_world.hbm_demo.features.f02_player_turn.handler import (
    handle_player_turn,
    run_debug_inject,
)
from agent_world.hbm_demo.features.f02_player_turn.inject import BAD_END_PUBLIC_MESSAGES
from agent_world.hbm_demo.features.f02_player_turn.inject import build_inject_events
from agent_world.hbm_demo.features.f02_player_turn.task import PendingTask, load_task, save_task
from agent_world.hbm_demo.features.f03_action_result.completion import (
    PHASE_RDC_PAIRS,
    check_action_complete,
    effective_tick_for_task,
    format_f2f_public_messages,
    format_messages,
)
from agent_world.hbm_demo.features.f03_action_result.handler import get_action_result
from agent_world.hbm_demo.features.f12_world_sync.handler import get_world_snapshot
from agent_world.hbm_demo.features.f13_world_loop_control.handler import (
    get_world_loop_status,
    pause_world_loop,
    resume_world_loop,
)
from agent_world.hbm_demo.features.f14_world_delta.handler import get_world_delta
from agent_world.hbm_demo.features.f04_stats.deltas import apply_stat_deltas, initial_stats
from agent_world.hbm_demo.features.f04_stats.scoring import (
    IMMEDIATE_MSG_PLACEHOLDER,
    generate_immediate_msg,
    score_player_turn,
)
from agent_world.hbm_demo.features.f06_read_model.world_db import (
    ReadOnlyWorldDB,
    SYSTEM_SENDER_NAME,
    make_readonly_db,
    sender_display_name,
)

__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_PHASE",
    "DEFAULT_PLACE_ID",
    "DEFAULT_SIM_ID",
    "INITIAL_STATS",
    "SESSION_KEY",
    "TASKS_KEY",
    "SYSTEM_SENDER_NAME",
    "PHASE_RDC_PAIRS",
    "BAD_END_PUBLIC_MESSAGES",
    "IMMEDIATE_MSG_PLACEHOLDER",
    "HbmSession",
    "PendingTask",
    "ReadOnlyWorldDB",
    "apply_stat_deltas",
    "build_inject_events",
    "check_action_complete",
    "create_session",
    "effective_tick_for_task",
    "format_f2f_public_messages",
    "format_messages",
    "generate_immediate_msg",
    "get_action_result",
    "get_world_snapshot",
    "get_world_delta",
    "get_world_loop_status",
    "pause_world_loop",
    "resume_world_loop",
    "get_name_map",
    "get_or_create_session",
    "get_scenario",
    "get_session_snapshot",
    "get_sim_dir",
    "get_world_db_path",
    "handle_player_turn",
    "initial_stats",
    "load_session",
    "load_task",
    "log_turn_event",
    "make_readonly_db",
    "reset_demo",
    "run_debug_inject",
    "save_session",
    "save_task",
    "score_player_turn",
    "sender_display_name",
]

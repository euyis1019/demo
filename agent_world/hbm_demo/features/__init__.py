"""HBM Demo business features (L2 orchestration layer).

Each subdirectory is one mergeable Feature; see dev_logs/26 for specs.
Public entrypoints: run_hbm.py, routes.py, game_service.py (see dev_logs/26 §5.1).
"""

from __future__ import annotations

from typing import Any, Dict

FEATURE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "F00": {
        "name": "平台核心 Runner",
        "status": "implemented",
        "path": "core/runner/",
        "modules": [
            "run_hbm",
            "kernel",
            "hbm_agent",
            "world_step",
            "seed",
            "ipc_handlers",
            "broadcast_helper",
        ],
    },
    "F01": {
        "name": "会话与重开",
        "status": "implemented",
        "path": "features/f01_session/",
        "modules": ["models", "lifecycle", "reset", "world_reset", "paths"],
    },
    "F02": {
        "name": "玩家回合 API1",
        "status": "implemented",
        "path": "features/f02_player_turn/",
        "modules": ["handler", "task", "inject"],
    },
    "F03": {
        "name": "动作结果 API2",
        "status": "implemented",
        "path": "features/f03_action_result/",
        "modules": ["handler", "completion"],
    },
    "F04": {
        "name": "数值与打分",
        "status": "implemented",
        "path": "features/f04_stats/",
        "modules": ["scoring", "deltas"],
    },
    "F05": {
        "name": "剧情路由",
        "status": "implemented",
        "path": "features/f05_story_routing/",
        "modules": ["routing"],
    },
    "F06": {
        "name": "只读世界模型",
        "status": "implemented",
        "path": "features/f06_read_model/",
        "modules": ["world_db"],
    },
    "F07": {
        "name": "Agent 行为控制栈（ABCS）",
        "status": "implemented",
        "path": "features/f07_agent_control/",
        "modules": [
            "turn_context",
            "knowledge",
            "llm_params",
            "player_response",
            "player_facing_f2f",
            "pick_active",
            "tool_guard",
            "inject_batch",
            "turn_control",
        ],
        "phase": "F07-E Step5 (final acceptance + Phase4 smoke)",
    },
    "F08": {
        "name": "HTTP 传输",
        "status": "implemented",
        "path": "http/",
        "modules": ["routes", "ipc_helper", "health", "http_errors"],
    },
    "F09": {
        "name": "前端三屏 UI",
        "status": "implemented",
        "path": "web/src/features/",
        "modules": [
            "boot",
            "game-loop",
            "layout",
            "main-chat",
            "observer",
            "endings",
            "api",
            "store",
        ],
    },
    "F10": {
        "name": "运维与启动",
        "status": "implemented",
        "path": "scripts/",
    },
    "F11": {
        "name": "回合内增量同步",
        "status": "implemented",
        "path": "features/f11_live_turn_sync/",
        "modules": ["handler", "async_inject", "task_state", "delta"],
        "phase": "F11-C done (frontend delta merge); feature complete",
    },
    "F12": {
        "name": "全量世界 UI 同步",
        "status": "in_progress",
        "path": "features/f12_world_sync/",
        "modules": [
            "delta",
            "snapshot",
            "formatter",
            "handler",
            "runner_bridge",
        ],
        "phase": "Phase 2 — Flask F12 API (world delta + world-snapshot)",
    },
}

__all__ = ["FEATURE_REGISTRY"]

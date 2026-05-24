"""HBM Demo business features (L2 orchestration layer).

Each subdirectory is one mergeable Feature; see dev_logs/26 for specs.
Root-level modules (routing.py, game_service.py, …) remain compatibility shims
until migration phase M2+ completes.
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
        "name": "Agent 行为控制 ABCS",
        "status": "design",
        "path": "features/f07_agent_control/",
        "doc": "dev_logs/24_HBM_Demo_Agent行为控制整合方案.md",
    },
    "F08": {
        "name": "HTTP 传输",
        "status": "planned",
        "path": "http/",
        "note": "M4 迁移",
    },
    "F09": {
        "name": "前端三屏 UI",
        "status": "implemented",
        "path": "web/src/",
    },
    "F10": {
        "name": "运维与启动",
        "status": "implemented",
        "path": "scripts/",
    },
}

__all__ = ["FEATURE_REGISTRY"]

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
        "modules": [
            "routing",
            "routing_config",
            "agent_signals",
            "story_signals",
            "watcher",
        ],
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
            "conversation_control",
            "inject_batch",
            "turn_control",
        ],
        "phase": "F07-E Step5 (final acceptance + Phase4 smoke)",
    },
    "F08V": {
        "name": "虚拟玩家 Agent（Virtual Player Entity）",
        "status": "implemented",
        "path": "features/f08_virtual_player/",
        "modules": ["player_entity", "player_f2f", "config", "phase_places"],
        "note": "编号 F08V 避免与 F08 HTTP 冲突；Phase R4 可选 rename → F17",
    },
    "F08": {
        "name": "HTTP 传输",
        "status": "implemented",
        "path": "http/",
        "modules": ["routes", "ipc_helper", "health", "http_errors"],
    },
    "F09": {
        "name": "前端 UI（双栏 WorldStage）",
        "status": "implemented",
        "path": "web/src/features/",
        "modules": [
            "boot",
            "game-loop",
            "layout",
            "main-chat",
            "world-stage",
            "story-mode",
            "prompt-trace",
            "endings",
            "shared",
            "store",
        ],
    },
    "F10": {
        "name": "运维与启动",
        "status": "implemented",
        "path": "scripts/ops/",
        "modules": ["start_demo", "stop_demo", "demo_ports"],
        "tests": "scripts/tests/test_m0.py",
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
        "status": "implemented",
        "path": "features/f12_world_sync/",
        "modules": [
            "delta",
            "snapshot",
            "formatter",
            "handler",
            "runner_bridge",
        ],
    },
    "F13": {
        "name": "世界 loop 暂停/继续",
        "status": "implemented",
        "path": "features/f13_world_loop_control/",
        "modules": ["handler"],
        "phase": "Phase 1b — pause/resume API + StatusPanel (dev_logs/31 §8.3)",
    },
    "F14": {
        "name": "常驻 world delta poll",
        "status": "implemented",
        "path": "features/f14_world_delta/",
        "modules": ["handler"],
        "phase": "Phase 2 — session delta + RoutingWatcher (dev_logs/31 §十四)",
    },
    "F15": {
        "name": "Prompt Inspector",
        "status": "implemented",
        "path": "features/f15_prompt_trace/",
        "modules": ["store", "linker", "handler", "refs"],
        "phase": "Phase 3 — trace DB + API + UI click-through (dev_logs/31 §十六)",
    },
    "F16": {
        "name": "WebSocket world delta stream",
        "status": "implemented",
        "path": "features/f16_world_stream/",
        "modules": ["handler", "config"],
        "phase": "Phase 5 — WS push delta (dev_logs/31 §14.4)",
    },
}

__all__ = ["FEATURE_REGISTRY"]

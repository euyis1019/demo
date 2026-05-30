"""F18 场景渲染 — 后端 Seedream 实时出图，替换剧情模式静态舞台。

事件驱动 + img2img 链：以上一帧为参考锁住角色/场景、只改动作，让世界"活起来"。

公共 API（L1/L3 只从这里导入，勿深引内部模块）。
"""

from __future__ import annotations

from agent_world.hbm_demo.features.f18_scene_render.config import (
    is_enabled,
    max_chain_depth,
    max_concurrent_renders,
)
from agent_world.hbm_demo.features.f18_scene_render.render import (
    FrameResult,
    SceneState,
    render_scene_frame,
    render_scene_frame_async,
)
from agent_world.hbm_demo.features.f18_scene_render.store import (
    clear_frames,
    read_latest_frame_data_uri,
    write_latest_frame,
)

__all__ = [
    "SceneState",
    "FrameResult",
    "render_scene_frame",
    "render_scene_frame_async",
    "is_enabled",
    "max_concurrent_renders",
    "max_chain_depth",
    "write_latest_frame",
    "read_latest_frame_data_uri",
    "clear_frames",
]

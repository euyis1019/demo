"""F18 场景渲染 — 后端文生图生成整帧游戏画面（替换前端静态渲染）。

公共 API（L1/L3 只从这里导入，勿深引内部模块）：
  - SceneState：与 Runner 解耦的轻量场景描述
  - FrameResult：出图结果（含 base64 / data_uri）
  - render_scene_frame / render_scene_frame_async：出一帧
  - is_enabled / min_tick_interval_sec：配置查询
"""

from __future__ import annotations

from agent_world.hbm_demo.features.f18_scene_render.config import (
    is_enabled,
    min_tick_interval_sec,
)
from agent_world.hbm_demo.features.f18_scene_render.render import (
    FrameResult,
    SceneState,
    render_scene_frame,
    render_scene_frame_async,
)

__all__ = [
    "SceneState",
    "FrameResult",
    "render_scene_frame",
    "render_scene_frame_async",
    "is_enabled",
    "min_tick_interval_sec",
]

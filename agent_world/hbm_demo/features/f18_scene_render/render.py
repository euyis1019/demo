"""F18 渲染编排：SceneState → prompt → 出图 → FrameResult（含 base64）。"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f18_scene_render import client as _client
from agent_world.hbm_demo.features.f18_scene_render.config import load_config
from agent_world.hbm_demo.features.f18_scene_render.consistency import seed_for_place
from agent_world.hbm_demo.features.f18_scene_render.prompt_builder import (
    build_scene_prompt,
)


@dataclass
class SceneState:
    """与 Runner 解耦的轻量场景描述（调用方负责从世界状态翻译过来）。"""

    tick: int
    place: str = "default"
    phase: Any = None
    occupant_count: int = 0
    has_speaker: bool = False
    speaker_id: Optional[int] = None  # 当前在玩家房间发言的 agent；None=无人发言
    line_seq: int = 0  # 台词序号：每句新台词 +1，使画面随台词更新


@dataclass
class FrameResult:
    tick: int
    ok: bool
    prompt: str = ""
    seed: int = 0
    model: str = ""
    mime: str = "image/jpeg"
    image_b64: Optional[str] = None
    elapsed_ms: int = 0
    error: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def data_uri(self) -> Optional[str]:
        if not self.image_b64:
            return None
        return f"data:{self.mime};base64,{self.image_b64}"


def _prepare(scene: SceneState):
    cfg = load_config()
    prompt = build_scene_prompt(
        {
            "tick": scene.tick,
            "place": scene.place,
            "phase": scene.phase,
            "occupant_count": scene.occupant_count,
            "has_speaker": scene.has_speaker,
            "speaker_id": scene.speaker_id,
        }
    )
    seed = seed_for_place(scene.place, int(cfg.get("seed_base", 7000)))
    return cfg, prompt, seed


def _to_result(scene: SceneState, cfg, prompt, seed, img, elapsed_ms) -> FrameResult:
    if not img.ok or not img.image_bytes:
        return FrameResult(
            tick=scene.tick, ok=False, prompt=prompt, seed=seed,
            model=str(cfg.get("model", "flux")), elapsed_ms=elapsed_ms,
            error=img.error or "render failed",
        )
    return FrameResult(
        tick=scene.tick, ok=True, prompt=prompt, seed=seed,
        model=str(cfg.get("model", "flux")), mime=img.mime,
        image_b64=base64.b64encode(img.image_bytes).decode("ascii"),
        elapsed_ms=elapsed_ms,
    )


def render_scene_frame(scene: SceneState) -> FrameResult:
    """同步出图（独立脚本 / P0 验证用）。"""
    cfg, prompt, seed = _prepare(scene)
    t0 = time.monotonic()
    img = _client.fetch_image_sync(
        prompt,
        width=int(cfg.get("width", 1280)), height=int(cfg.get("height", 720)),
        seed=seed, model=str(cfg.get("model", "flux")),
        nologo=bool(cfg.get("nologo", True)),
        timeout_sec=float(cfg.get("timeout_sec", 60)),
    )
    return _to_result(scene, cfg, prompt, seed, img, int((time.monotonic() - t0) * 1000))


async def render_scene_frame_async(scene: SceneState) -> FrameResult:
    """异步出图（P1 接入 tick 循环用，不阻塞事件循环）。"""
    cfg, prompt, seed = _prepare(scene)
    t0 = time.monotonic()
    img = await _client.fetch_image(
        prompt,
        width=int(cfg.get("width", 1280)), height=int(cfg.get("height", 720)),
        seed=seed, model=str(cfg.get("model", "flux")),
        nologo=bool(cfg.get("nologo", True)),
        timeout_sec=float(cfg.get("timeout_sec", 60)),
    )
    return _to_result(scene, cfg, prompt, seed, img, int((time.monotonic() - t0) * 1000))

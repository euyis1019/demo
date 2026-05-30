"""F18 渲染编排：SceneState → prompt → Seedream(t2i/img2img) → FrameResult。

无 ref_image_url → 文生图锚定帧；有 ref_image_url → 图生图（锁角色、改动作）。
出图为 2K，下发前用 Pillow 降到 output_width×height 再 base64，省带宽。
"""

from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f18_scene_render import client as _client
from agent_world.hbm_demo.features.f18_scene_render.config import load_config
from agent_world.hbm_demo.features.f18_scene_render.consistency import seed_for_place
from agent_world.hbm_demo.features.f18_scene_render.prompt_builder import (
    build_action_prompt,
    build_anchor_prompt,
)


@dataclass
class SceneState:
    """与 Runner 解耦的轻量场景描述（调用方负责从世界状态翻译过来）。"""

    tick: int
    place: str = "default"
    phase: Any = None
    occupant_count: int = 0
    has_speaker: bool = False
    speaker_id: Optional[int] = None
    speaker_line: Optional[str] = None  # 说话人当前真实台词（喂进 prompt，让画面体现实际对话/动作）


@dataclass
class FrameResult:
    tick: int
    ok: bool
    mime: str = "image/jpeg"
    image_b64: Optional[str] = None
    url: str = ""  # Seedream 源图 url（作为下一帧 img2img 参考）
    elapsed_ms: int = 0
    error: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def data_uri(self) -> Optional[str]:
        if not self.image_b64:
            return None
        return f"data:{self.mime};base64,{self.image_b64}"


def _downscale_jpeg(raw: bytes, width: int, height: int) -> bytes:
    """2K 出图降到 720p（cover 裁切），减小 base64 体积。Pillow 不可用则原样返回。"""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(raw)).convert("RGB")
        src_w, src_h = img.size
        scale = max(width / src_w, height / src_h)
        img = img.resize((round(src_w * scale), round(src_h * scale)), Image.LANCZOS)
        left = (img.width - width) // 2
        top = (img.height - height) // 2
        img = img.crop((left, top, left + width, top + height))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        return buf.getvalue()
    except Exception:
        return raw


def _call(scene: SceneState, ref_image_url: Optional[str]):
    cfg = load_config()
    from agent_world.hbm_demo.features.f18_scene_render.config import api_key

    if ref_image_url:
        prompt, seed = build_action_prompt(_as_dict(scene)), None
    else:
        prompt = build_anchor_prompt(_as_dict(scene))
        seed = seed_for_place(scene.place, int(cfg.get("seed_base", 7000)))
    return cfg, prompt, seed, api_key()


def _as_dict(scene: SceneState) -> Dict[str, Any]:
    return {
        "place": scene.place,
        "phase": scene.phase,
        "occupant_count": scene.occupant_count,
        "has_speaker": scene.has_speaker,
        "speaker_id": scene.speaker_id,
        "speaker_line": scene.speaker_line,
    }


def _finish(scene: SceneState, cfg, img, t0) -> FrameResult:
    elapsed = int((time.monotonic() - t0) * 1000)
    if not img.ok or not img.image_bytes:
        return FrameResult(tick=scene.tick, ok=False, url=img.url, elapsed_ms=elapsed,
                           error=img.error or "render failed")
    small = _downscale_jpeg(
        img.image_bytes, int(cfg.get("output_width", 1280)), int(cfg.get("output_height", 720))
    )
    return FrameResult(
        tick=scene.tick, ok=True, mime="image/jpeg",
        image_b64=base64.b64encode(small).decode("ascii"),
        url=img.url, elapsed_ms=elapsed,
    )


async def render_scene_frame_async(
    scene: SceneState, ref_image_url: Optional[str] = None
) -> FrameResult:
    cfg, prompt, seed, key = _call(scene, ref_image_url)
    t0 = time.monotonic()
    img = await _client.generate(
        prompt, endpoint=str(cfg["endpoint"]), model=str(cfg["model"]), api_key=key,
        size=str(cfg.get("size", "2560x1440")), watermark=bool(cfg.get("watermark", False)),
        timeout_sec=float(cfg.get("timeout_sec", 60)), seed=seed, ref_image_url=ref_image_url,
    )
    return _finish(scene, cfg, img, t0)


def render_scene_frame(scene: SceneState, ref_image_url: Optional[str] = None) -> FrameResult:
    """同步出图（独立脚本 / 烟测用）。"""
    cfg, prompt, seed, key = _call(scene, ref_image_url)
    t0 = time.monotonic()
    img = _client.generate_sync(
        prompt, endpoint=str(cfg["endpoint"]), model=str(cfg["model"]), api_key=key,
        size=str(cfg.get("size", "2560x1440")), watermark=bool(cfg.get("watermark", False)),
        timeout_sec=float(cfg.get("timeout_sec", 60)), seed=seed, ref_image_url=ref_image_url,
    )
    return _finish(scene, cfg, img, t0)

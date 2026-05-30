"""世界状态 → 一句画面 prompt（消费 L0 scene_prompt.yaml 片段）。

输入是与 Runner 解耦的轻量 SceneState（见 __init__.SceneState），不直接依赖
kernel/world_state；由调用方(P1 的 hook)把世界状态翻译成 SceneState 后传入。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f18_scene_render.config import load_prompt_template


def _place_scene(tpl: Dict[str, Any], place_id: str) -> str:
    places = tpl.get("places") or {}
    return places.get(place_id) or places.get("default") or "modern office space"


def _phase_key(phase: Any) -> str:
    """把 "Phase 3" / "3" / 3 统一成数字 key "3"；取不到则 default。"""
    m = re.search(r"\d+", str(phase or ""))
    return m.group(0) if m else "default"


def _phase_mood(tpl: Dict[str, Any], phase: Any) -> str:
    moods = tpl.get("phase_mood") or {}
    return moods.get(_phase_key(phase)) or moods.get("default") or "neutral office mood"


def _role_for(tpl: Dict[str, Any], speaker_id: Optional[int]) -> str:
    roles = tpl.get("agent_roles") or {}
    if speaker_id is None:
        return roles.get("default") or "a businessperson"
    return roles.get(str(speaker_id)) or roles.get("default") or "a businessperson"


def _occupants_desc(tpl: Dict[str, Any], scene: Dict[str, Any]) -> str:
    occupant_count = int(scene.get("occupant_count") or 0)
    if occupant_count <= 0:
        return tpl.get("empty_room") or "an empty room"
    parts = [
        (tpl.get("occupants_template") or "{count} business people in the room").format(
            count=occupant_count
        )
    ]
    # 有人发言 → 体现"谁在说话"
    if scene.get("has_speaker"):
        role = _role_for(tpl, scene.get("speaker_id"))
        spk_tpl = tpl.get("speaker_template") or "{role} is speaking"
        parts.append(spk_tpl.format(role=role))
    return ", ".join(parts)


def build_scene_prompt(scene: Dict[str, Any]) -> str:
    """scene: {place, phase, occupant_count, has_speaker, speaker_id, tick}."""
    tpl = load_prompt_template()
    style = tpl.get("style_prefix") or "cinematic photorealistic photograph"
    place_scene = _place_scene(tpl, str(scene.get("place") or "default"))
    mood = _phase_mood(tpl, scene.get("phase"))
    occupants = _occupants_desc(tpl, scene)
    prompt = f"{style}, {place_scene}, {occupants}, {mood}"
    # 时间扰动：用世界 tick 做轻微"瞬间"扰动，世界运行时每 tick 刷新画面
    moment_tpl = tpl.get("moment_template")
    if moment_tpl:
        prompt = f"{prompt}, {moment_tpl.format(tick=int(scene.get('tick') or 0))}"
    negative = tpl.get("negative")
    if negative:
        prompt = f"{prompt} | {negative}"
    return " ".join(prompt.split())  # 折叠多余空白

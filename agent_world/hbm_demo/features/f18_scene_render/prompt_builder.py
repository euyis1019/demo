"""世界状态 → 一句画面 prompt（消费 L0 scene_prompt.yaml 片段）。

输入是与 Runner 解耦的轻量 SceneState（见 __init__.SceneState），不直接依赖
kernel/world_state；由调用方(P1 的 hook)把世界状态翻译成 SceneState 后传入。
"""

from __future__ import annotations

from typing import Any, Dict

from agent_world.hbm_demo.features.f18_scene_render.config import load_prompt_template


def _place_scene(tpl: Dict[str, Any], place_id: str) -> str:
    places = tpl.get("places") or {}
    return places.get(place_id) or places.get("default") or "modern office space"


def _phase_mood(tpl: Dict[str, Any], phase: Any) -> str:
    moods = tpl.get("phase_mood") or {}
    return moods.get(str(phase)) or moods.get("default") or "neutral office mood"


def _occupants_desc(tpl: Dict[str, Any], occupant_count: int, has_speaker: bool) -> str:
    if occupant_count <= 0:
        return tpl.get("empty_room") or "an empty room"
    parts = []
    occ_tpl = tpl.get("occupants_template") or "{count} business people in the room"
    parts.append(occ_tpl.format(count=occupant_count))
    if has_speaker:
        parts.append(tpl.get("speaker_template") or "one person speaking")
    return ", ".join(parts)


def build_scene_prompt(scene: Dict[str, Any]) -> str:
    """scene: {place, phase, occupant_count, has_speaker}. 返回完整 prompt 串。"""
    tpl = load_prompt_template()
    style = tpl.get("style_prefix") or "flat illustration cartoon style"
    place_scene = _place_scene(tpl, str(scene.get("place") or "default"))
    mood = _phase_mood(tpl, scene.get("phase"))
    occupants = _occupants_desc(
        tpl,
        int(scene.get("occupant_count") or 0),
        bool(scene.get("has_speaker")),
    )
    prompt = f"{style}, {place_scene}, {occupants}, {mood}"
    negative = tpl.get("negative")
    if negative:
        prompt = f"{prompt} | {negative}"
    return " ".join(prompt.split())  # 折叠多余空白

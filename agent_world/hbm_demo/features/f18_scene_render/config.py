"""Load F18 scene-render config (model params +画面 prompt 模板) from L0."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict

import yaml

from agent_world.hbm_demo.shared.prompt_paths import (
    scene_render_config_path,
    scene_render_prompt_path,
)

_DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "provider": "pollinations",
    "model": "flux",
    "width": 1280,
    "height": 720,
    "seed_base": 7000,
    "timeout_sec": 30,
    "nologo": True,
    "min_tick_interval_sec": 1.5,
    "render_wait_cap_sec": 6.0,
}


@lru_cache(maxsize=1)
def load_config() -> Dict[str, Any]:
    path = scene_render_config_path()
    if not path.is_file():
        return dict(_DEFAULT_CONFIG)
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    block = data.get("scene_render") if isinstance(data, dict) else {}
    merged = dict(_DEFAULT_CONFIG)
    if isinstance(block, dict):
        merged.update(block)
    return merged


@lru_cache(maxsize=1)
def load_prompt_template() -> Dict[str, Any]:
    path = scene_render_prompt_path()
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    block = data.get("scene_prompt") if isinstance(data, dict) else {}
    return dict(block) if isinstance(block, dict) else {}


def is_enabled() -> bool:
    # 门禁/E2E 用环境变量强制关闭，避免世界 tick 依赖外部出图 API。
    if os.environ.get("HBM_SCENE_RENDER_DISABLED") == "1":
        return False
    return bool(load_config().get("enabled", True))


def min_tick_interval_sec() -> float:
    return float(load_config().get("min_tick_interval_sec", 1.5))


def render_wait_cap_sec() -> float:
    return float(load_config().get("render_wait_cap_sec", 6.0))

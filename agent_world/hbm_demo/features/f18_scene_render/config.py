"""Load F18 scene-render config (Seedream 模型参数 + 画面 prompt 模板) from L0."""

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
    "provider": "seedream",
    "model": "doubao-seedream-4-5-251128",
    "endpoint": "https://ark.cn-beijing.volces.com/api/v3/images/generations",
    "api_key_env": "ARK_API_KEY",
    "size": "2560x1440",
    "output_width": 1280,
    "output_height": 720,
    "seed_base": 7000,
    "watermark": False,
    "timeout_sec": 60,
    "max_concurrent_renders": 4,
    "max_chain_depth": 8,
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
    # 门禁/E2E 用环境变量强制关闭，避免世界依赖外部出图 API。
    if os.environ.get("HBM_SCENE_RENDER_DISABLED") == "1":
        return False
    return bool(load_config().get("enabled", True))


def api_key() -> str:
    return str(os.environ.get(str(load_config().get("api_key_env", "ARK_API_KEY"))) or "").strip()


def max_concurrent_renders() -> int:
    return max(1, int(load_config().get("max_concurrent_renders", 4)))


def max_chain_depth() -> int:
    return int(load_config().get("max_chain_depth", 8))

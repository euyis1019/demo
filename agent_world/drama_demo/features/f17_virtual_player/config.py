"""F17 virtual player configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict

import yaml

from agent_world.drama_demo.shared.prompt_paths import virtual_player_config_path


@lru_cache(maxsize=1)
def load_f08_config() -> Dict[str, Any]:
    path = virtual_player_config_path()
    if not path.is_file():
        return {"enabled": False, "player_agent_id": 0}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return dict(data)


def is_f08_enabled() -> bool:
    return bool(load_f08_config().get("enabled", False))


def player_agent_id() -> int:
    return int(load_f08_config().get("player_agent_id", 0))

"""F08 virtual player configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

_F08_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = _F08_DIR / "config.yaml"


@lru_cache(maxsize=1)
def load_f08_config() -> Dict[str, Any]:
    if not _CONFIG_PATH.is_file():
        return {"enabled": False, "player_agent_id": 0}
    with _CONFIG_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return dict(data)


def is_f08_enabled() -> bool:
    return bool(load_f08_config().get("enabled", False))


def player_agent_id() -> int:
    return int(load_f08_config().get("player_agent_id", 0))

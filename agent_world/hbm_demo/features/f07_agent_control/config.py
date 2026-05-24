"""Load F07 turn_control.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

_HBM_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TURN_CONTROL_PATH = _HBM_ROOT / "turn_control.yaml"


@lru_cache(maxsize=1)
def load_turn_control(path: Path | None = None) -> Dict[str, Any]:
    cfg_path = path or DEFAULT_TURN_CONTROL_PATH
    with cfg_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return dict(data)


def is_abcs_enabled(path: Path | None = None) -> bool:
    return bool(load_turn_control(path).get("enabled", True))

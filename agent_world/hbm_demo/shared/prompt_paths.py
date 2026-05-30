"""Central paths for agent prompt / story YAML (dev_logs/38 R4/R5)."""

from __future__ import annotations

from pathlib import Path

_HBM_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_ROOT = _HBM_ROOT / "config" / "prompts"


def turn_control_path() -> Path:
    return PROMPTS_ROOT / "abcs" / "turn_control.yaml"


def story_knowledge_dir() -> Path:
    return PROMPTS_ROOT / "abcs" / "story_knowledge"


def routing_config_path() -> Path:
    return PROMPTS_ROOT / "routing" / "routing.yaml"


def virtual_player_config_path() -> Path:
    return PROMPTS_ROOT / "virtual_player" / "config.yaml"


def virtual_player_phase_places_path() -> Path:
    return PROMPTS_ROOT / "virtual_player" / "phase_places.yaml"


def scenario_path() -> Path:
    return _HBM_ROOT / "hbm_scenario.yaml"


def scene_render_config_path() -> Path:
    return PROMPTS_ROOT / "scene_render" / "config.yaml"


def scene_render_prompt_path() -> Path:
    return PROMPTS_ROOT / "scene_render" / "scene_prompt.yaml"

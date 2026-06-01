"""Story Pack 落盘器（dev_logs/45 §1.3 orchestrator 的落盘核心）。

把内存里的 pack sections（dict）写成 config/stories/<id>/*.yaml。写前过 assert_safe_target
红线（绝不写 sim/ 或包源码）。幂等：同样输入产生同样文件。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from agent_world.drama_demo.tools.story_studio.safety import assert_safe_target

# section 名 → 文件名。仅写出 sections 里存在的键。
_SECTION_FILES = {
    "meta": "meta.yaml",
    "berts": "berts.yaml",
    "story_graph": "story_graph.yaml",  # 旧包兼容；新包不再产出（剧情由 berts 驱动）
    "places": "places.yaml",
    "agents": "agents.yaml",
    "relations": "relations.yaml",
    "relation_types": "relation_types.yaml",
    "groups": "groups.yaml",
    "signals": "signals.yaml",
    "endings": "endings.yaml",
    "judges": "judges.yaml",
    "timed_events": "timed_events.yaml",
    "language_style": "language_style.yaml",
    "ui_text": "ui_text.yaml",
}


def _dump(data: Any) -> str:
    return yaml.safe_dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)


def write_story_pack(sections: Dict[str, Any], target_dir: Path) -> Path:
    """把 sections 写成 Story Pack 文件，返回写入目录。target_dir 过安全红线。"""
    target = assert_safe_target(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    for name, payload in sections.items():
        filename = _SECTION_FILES.get(name)
        if filename is None:
            continue  # 未知 section 名跳过（前向兼容）
        (target / filename).write_text(_dump(payload), encoding="utf-8")
    return target

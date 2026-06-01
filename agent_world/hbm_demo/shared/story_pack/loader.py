"""Story Pack 加载器：从 config/stories/<id>/ 读 YAML（dev_logs/42 §3）。

本切片仅加载 meta.yaml + story_graph.yaml（G0 第一竖切）。后续切片再补
places/agents/relations/... 的加载与跨文件引用闭合校验（dev_logs/46 C 类）。
纯 IO + 解析，无业务规则（D3：shared 不依赖 features）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

from agent_world.hbm_demo.shared.prompt_paths import stories_root, story_dir
from agent_world.hbm_demo.shared.story_pack.errors import StoryPackError
from agent_world.hbm_demo.shared.story_pack.graph import StoryGraph


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise StoryPackError(f"Story Pack 文件不存在：{path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise StoryPackError(f"{path} 顶层必须是 mapping，实际为 {type(data).__name__}")
    return data


def list_story_ids() -> List[str]:
    """发现 config/stories/ 下的全部 Story Pack（含 meta.yaml + story_graph.yaml 的目录）。"""
    root = stories_root()
    if not root.is_dir():
        return []
    out: List[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "meta.yaml").is_file() and (child / "story_graph.yaml").is_file():
            out.append(child.name)
    return out


def load_meta(story_id: str) -> Dict[str, Any]:
    """读 meta.yaml（simulation_id / initial / player / clock / llm 引用）。"""
    return _load_yaml(story_dir(story_id) / "meta.yaml")


def load_story_graph(story_id: str) -> StoryGraph:
    """读 story_graph.yaml 并构造 StoryGraph（不自动 validate，调用方决定时机）。"""
    data = _load_yaml(story_dir(story_id) / "story_graph.yaml")
    return StoryGraph.from_mapping(data)

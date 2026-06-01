"""Story Pack 加载器：从 config/stories/<id>/ 读 YAML（dev_logs/42 §3 / dev_logs/48）。

加载 meta.yaml + berts.yaml（剧情主载体）+ 可选 story_graph.yaml（旧包兼容，缺则空图）
+ places/agents/relations/... 世界原语文件。纯 IO + 解析，无业务规则（D3：shared 不依赖 features）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

from agent_world.drama_demo.shared.prompt_paths import stories_root, story_dir
from agent_world.drama_demo.shared.story_pack.bert import BertSet
from agent_world.drama_demo.shared.story_pack.errors import StoryPackError
from agent_world.drama_demo.shared.story_pack.graph import StoryGraph


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise StoryPackError(f"Story Pack 文件不存在：{path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise StoryPackError(f"{path} 顶层必须是 mapping，实际为 {type(data).__name__}")
    return data


def list_story_ids() -> List[str]:
    """发现 config/stories/ 下的全部 Story Pack（含 meta.yaml + berts.yaml 的目录）。

    bert（条件→反应）驱动后，剧情结构在 berts.yaml；旧包的 story_graph.yaml 也接受（向后兼容）。
    """
    root = stories_root()
    if not root.is_dir():
        return []
    out: List[str] = []
    for child in sorted(root.iterdir()):
        if not (child.is_dir() and (child / "meta.yaml").is_file()):
            continue
        if (child / "berts.yaml").is_file() or (child / "story_graph.yaml").is_file():
            out.append(child.name)
    return out


def load_meta(story_id: str) -> Dict[str, Any]:
    """读 meta.yaml（simulation_id / initial / player / clock / llm 引用）。"""
    return _load_yaml(story_dir(story_id) / "meta.yaml")


def load_story_graph(story_id: str) -> StoryGraph:
    """读 story_graph.yaml 并构造 StoryGraph；文件缺失则返回空图（bert 驱动包无 story_graph）。"""
    path = story_dir(story_id) / "story_graph.yaml"
    if not path.is_file():
        return StoryGraph.empty()
    return StoryGraph.from_mapping(_load_yaml(path))


def load_berts(story_id: str) -> BertSet:
    """读 berts.yaml 并构造 BertSet（bert「条件→反应」规则集）；文件缺失则返回空集（降级）。

    bert 取代旧的 story_graph 任务/节点结构：剧情由「玩家做某事→某 NPC 反应」的规则驱动。
    迁移期两者可并存（旧包仍有 story_graph，新包有 berts）；不自动 validate。
    """
    path = story_dir(story_id) / "berts.yaml"
    if not path.is_file():
        return BertSet()
    return BertSet.from_mapping(_load_yaml(path))

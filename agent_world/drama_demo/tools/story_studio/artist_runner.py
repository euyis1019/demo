"""跑 Artist 管理 agent：给某个故事出齐图片资源 + 自审 + 查数量是否足够。

红线：只写 config/stories/<id>/（assert_safe_target），绝不碰 sim/（玩家存档）。
"""

from __future__ import annotations

from typing import Optional

from agent_world.drama_demo.shared.prompt_paths import story_dir
from agent_world.drama_demo.shared.story_pack import load_and_validate_story_pack
from agent_world.drama_demo.tools.story_studio.agents.artist import Artist, ArtReport
from agent_world.drama_demo.tools.story_studio.safety import assert_safe_target


def generate_story_assets(
    story_id: str, *, only_missing: bool = True, limit: Optional[int] = None, review: bool = True,
) -> ArtReport:
    """给 story_id 出齐 Story Pack 需要的图片资源。需求/数量来自 Story Pack（设计 agent 的产出）。"""
    pack = load_and_validate_story_pack(story_id)  # 带病包不出图
    asset_dir = assert_safe_target(story_dir(story_id))  # 红线：只落 config/stories/<id>/
    return Artist(review=review).run(pack, asset_dir, only_missing=only_missing, limit=limit)

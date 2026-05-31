#!/usr/bin/env python3
"""通用 Story Pack 校验 CLI（dev_logs/45 §4 validate 闸门 / dev_logs/46 C-3）。

对**任意** Story Pack 跑加载 + 结构(V) + 跨文件引用闭合(X) 校验——不写死任何 HBM 常量。
设计期生成工具与运行期加载共用同一闸门；本 CLI 供人工/CI 调用。

用法：
  python3 agent_world/hbm_demo/scripts/ops/validate_story_pack.py            # 校验全部 pack
  python3 agent_world/hbm_demo/scripts/ops/validate_story_pack.py <story_id> # 校验单个
退出码：0 全过；1 有 pack 校验失败；2 指定 id 不存在。
"""

from __future__ import annotations

import sys
from typing import List

from agent_world.hbm_demo.shared.story_pack import list_story_ids, load_story_pack
from agent_world.hbm_demo.shared.story_pack.errors import StoryPackError


def validate_one(story_id: str) -> List[str]:
    """返回 story_id 的违例列表（空 = 通过）。加载异常也并入违例。"""
    try:
        pack = load_story_pack(story_id)
    except StoryPackError as exc:
        return [f"[LOAD] {exc}"]
    return pack.validate()


def main(argv: List[str]) -> int:
    targets = argv[1:] if len(argv) > 1 else list_story_ids()
    if not targets:
        print("未发现任何 Story Pack（config/stories/ 为空）")
        return 0

    known = set(list_story_ids())
    total_fail = 0
    for story_id in targets:
        if story_id not in known:
            print(f"✗ {story_id}: 不存在该 Story Pack")
            return 2
        issues = validate_one(story_id)
        if issues:
            total_fail += 1
            print(f"✗ {story_id}: {len(issues)} 项违例")
            for it in issues:
                print(f"    {it}")
        else:
            pack = load_story_pack(story_id)
            print(
                f"✓ {story_id}: 通过"
                f"（{len(pack.graph.nodes)} 节点 / {len(pack.graph.endings)} 结局 / "
                f"{len(pack.graph.edges)} 边 / {len(pack.agent_ids())} agent / {len(pack.place_ids())} 地点）"
            )
    print(f"\n校验：{len(targets) - total_fail}/{len(targets)} 个 Story Pack 通过")
    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

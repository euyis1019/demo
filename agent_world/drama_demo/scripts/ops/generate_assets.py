#!/usr/bin/env python3
"""CLI：给某个故事用文生图模型(Seedream)生成图片资源——Artist 管理 agent。

用法：
    python3 -m agent_world.drama_demo.scripts.ops.generate_assets canglan_sword
    python3 -m agent_world.drama_demo.scripts.ops.generate_assets canglan_sword --all
    python3 -m agent_world.drama_demo.scripts.ops.generate_assets canglan_sword --limit 2

需在 agent_world/drama_demo/.env 配置 ARK_API_KEY=ark-...（火山 Ark），否则提示配置。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _load_env() -> None:
    env = Path(__file__).resolve().parents[2] / ".env"
    if env.is_file():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)


def main(argv=None) -> int:
    _load_env()
    p = argparse.ArgumentParser(description="给故事生成图片资源（Artist agent）")
    p.add_argument("story_id")
    p.add_argument("--all", action="store_true", help="重出全部（默认只补缺的）")
    p.add_argument("--limit", type=int, default=None, help="只出前 N 张（调试）")
    p.add_argument("--no-review", action="store_true", help="跳过自审")
    args = p.parse_args(argv)

    from agent_world.drama_demo.tools.story_studio.artist_runner import generate_story_assets
    from agent_world.drama_demo.tools.story_studio.image_client import ImageKeyMissing

    print(f"=== Artist：为《{args.story_id}》出图 ===")
    try:
        rep = generate_story_assets(
            args.story_id, only_missing=not args.all, limit=args.limit, review=not args.no_review,
        )
    except ImageKeyMissing as exc:
        print(f"\n✗ {exc}")
        return 2

    icon = {"present": "·", "ok": "✓", "reject": "✗", "failed": "✗"}
    for it in rep.items:
        print(f"  {icon.get(it.status, '?')} [{it.status}] {it.spec.label}")
        if it.note:
            print(f"      {it.note[:100]}")
    print("\n--- 数量足够性（由 Story Pack 即设计 agent 的需求决定）---")
    print(f"  需求 {rep.required} 张 / 已就位 {rep.present} 张 / 缺 {len(rep.missing)} 张")
    if rep.missing:
        print(f"  缺：{rep.missing}")
    print("  ✅ 资源足够，故事可跑起来" if rep.enough else "  ⚠️  资源不足，故事缺图")
    return 0 if rep.enough else 1


if __name__ == "__main__":
    sys.exit(main())

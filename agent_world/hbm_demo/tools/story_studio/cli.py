#!/usr/bin/env python3
"""story_studio CLI（dev_logs/45 §1.3）。G1 落地子命令：validate-brief / compile / generate(占位)。

用法：
  python3 -m agent_world.hbm_demo.tools.story_studio.cli validate-brief <brief.yaml>
  python3 -m agent_world.hbm_demo.tools.story_studio.cli compile <story_id> <sections.(yaml|json)>
  python3 -m agent_world.hbm_demo.tools.story_studio.cli generate <brief.yaml>   # G2 实现(需 LLM)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

import yaml

from agent_world.hbm_demo.tools.story_studio.brief_schema import validate_brief
from agent_world.hbm_demo.tools.story_studio.orchestrator import compile_pack


def _load_any(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    return yaml.safe_load(text) or {}


def _cmd_validate_brief(args: argparse.Namespace) -> int:
    issues = validate_brief(_load_any(Path(args.brief)))
    if issues:
        print(f"✗ brief 校验未过（{len(issues)} 项）：")
        for it in issues:
            print(f"    {it}")
        return 1
    print("✓ brief 校验通过")
    return 0


def _cmd_compile(args: argparse.Namespace) -> int:
    sections = _load_any(Path(args.sections))
    result = compile_pack(sections, story_id=args.story_id)
    if result.ok:
        print(f"✓ 已编译 Story Pack '{args.story_id}' → {result.target_dir}（validate 通过）")
        return 0
    print(f"✗ Story Pack '{args.story_id}' validate 未过（{len(result.issues)} 项）：")
    for it in result.issues:
        print(f"    {it}")
    return 1


def _cmd_review(args: argparse.Namespace) -> int:
    from agent_world.hbm_demo.shared.story_pack import list_story_ids, load_story_pack
    from agent_world.hbm_demo.tools.story_studio.review import render_review

    if args.story_id not in list_story_ids():
        print(f"✗ 不存在 Story Pack '{args.story_id}'")
        return 2
    print(render_review(load_story_pack(args.story_id)))
    return 0


def _cmd_regenerate(args: argparse.Namespace) -> int:
    from agent_world.hbm_demo.tools.story_studio.base_agent import StoryStudioError
    from agent_world.hbm_demo.tools.story_studio.llm_client import make_llm_client
    from agent_world.hbm_demo.tools.story_studio.orchestrator import regenerate_writer

    if args.section != "writer":
        print(f"暂仅支持局部重生成 section=writer（你给的是 {args.section}）。")
        return 2
    try:
        client = make_llm_client()
        result = regenerate_writer(args.story_id, client=client)
    except (StoryStudioError, RuntimeError) as exc:
        print(f"✗ 局部重生成失败：{exc}")
        return 1
    print(f"{'✓' if result.ok else '✗'} 已局部重生成 '{args.story_id}' 的 writer 层（{result.target_dir}）")
    return 0 if result.ok else 1


def _cmd_assets(args: argparse.Namespace) -> int:
    from agent_world.hbm_demo.shared.story_pack import list_story_ids, load_story_pack
    from agent_world.hbm_demo.tools.story_studio.asset_manifest import (
        render_asset_manifest,
        write_asset_manifest,
    )

    if args.story_id not in list_story_ids():
        print(f"✗ 不存在 Story Pack '{args.story_id}'")
        return 2
    pack = load_story_pack(args.story_id)
    if args.write:
        path = write_asset_manifest(pack)
        print(f"✓ 已写素材清单 → {path}")
    else:
        print(render_asset_manifest(pack))
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    brief = _load_any(Path(args.brief))
    issues = validate_brief(brief)
    if issues:
        print(f"✗ brief 校验未过（{len(issues)} 项），先修 brief：")
        for it in issues:
            print(f"    {it}")
        return 1
    from agent_world.hbm_demo.tools.story_studio.base_agent import StoryStudioError
    from agent_world.hbm_demo.tools.story_studio.llm_client import make_llm_client
    from agent_world.hbm_demo.tools.story_studio.orchestrator import generate

    try:
        client = make_llm_client(brief.get("llm"))
        result = generate(brief, story_id=args.story_id, client=client, max_rounds=args.max_rounds)
    except StoryStudioError as exc:
        print(f"✗ 生成失败：{exc}")
        return 1
    except RuntimeError as exc:  # 缺 key 等
        print(f"✗ {exc}")
        return 1
    print(f"✓ 已生成 Story Pack '{args.story_id}' → {result.target_dir}（G2 骨架级；G3 补全世界原语）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="story_studio", description="设计期 Story Pack 生成工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    pb = sub.add_parser("validate-brief", help="校验 story brief")
    pb.add_argument("brief")
    pb.set_defaults(func=_cmd_validate_brief)

    pc = sub.add_parser("compile", help="由 sections 编译 Story Pack 并校验")
    pc.add_argument("story_id")
    pc.add_argument("sections")
    pc.set_defaults(func=_cmd_compile)

    pg = sub.add_parser("generate", help="由 brief 经 Designer + validate 回路生成 Story Pack 骨架")
    pg.add_argument("story_id")
    pg.add_argument("brief")
    pg.add_argument("--max-rounds", type=int, default=3, dest="max_rounds")
    pg.set_defaults(func=_cmd_generate)

    pr = sub.add_parser("review", help="审阅 Story Pack（ASCII 故事图 + 校验报告）")
    pr.add_argument("story_id")
    pr.set_defaults(func=_cmd_review)

    prg = sub.add_parser("regenerate", help="局部重生成（section=writer：只重产触发/注入/signals）")
    prg.add_argument("story_id")
    prg.add_argument("section", choices=["writer"])
    prg.set_defaults(func=_cmd_regenerate)

    pa = sub.add_parser("assets", help="生成图片素材清单 txt（列出需要的图 + 详细提示词，用户自备）")
    pa.add_argument("story_id")
    pa.add_argument("--write", action="store_true", help="写入 <story>/ASSETS_TODO.txt（默认仅打印）")
    pa.set_defaults(func=_cmd_assets)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

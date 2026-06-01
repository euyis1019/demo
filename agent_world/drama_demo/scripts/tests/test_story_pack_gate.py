#!/usr/bin/env python3
"""通用 Story Pack 验收门禁（dev_logs/46 C-3：替代 test_m0 写死 HBM 常量）。

对 config/stories/ 下**每一个** Story Pack 跑校验闸门——不依赖任何 HBM 专属断言。
新加一个故事包就自动纳入门禁；任何包校验不过即红。纯数据层，不起 Runner/Flask/LLM。
"""

from __future__ import annotations

import sys

from agent_world.drama_demo.scripts.ops.validate_story_pack import main as cli_main
from agent_world.drama_demo.shared.story_pack import list_story_ids, load_story_pack


def test_present_packs_only() -> None:
    """生成优先：config/stories/ 可以为空（故事由管理 agent 按需生成，不再写死任何默认故事）。
    若存在 Story Pack，则每个都必须过校验（见 test_all_packs_validate）；这里只做信息性列举，不强求存在。"""
    ids = list_story_ids()
    print(f"    （config/stories 现有 {len(ids)} 个包：{ids or '空 → 生成优先，正常'}）")


def test_all_packs_validate() -> None:
    failures = {}
    for story_id in list_story_ids():
        issues = load_story_pack(story_id).validate()
        if issues:
            failures[story_id] = issues
    assert not failures, f"以下 Story Pack 校验未通过：{failures}"


def test_cli_passes_for_all() -> None:
    assert cli_main(["validate_story_pack"]) == 0


def test_cli_unknown_id_returns_2() -> None:
    assert cli_main(["validate_story_pack", "no_such_story"]) == 2


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {fn.__name__}: {exc}")
    print(f"\nStory Pack 验收门禁：{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

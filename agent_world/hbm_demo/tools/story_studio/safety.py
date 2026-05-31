"""story_studio 安全红线（dev_logs/45 §1.2 / CLAUDE.md §6）。

机制级保证：生成工具**只写 config/stories/<id>/，绝不写 sim/(玩家存档) 或包源码目录**。
写盘前一律过 assert_safe_target；红线靠断言而非自觉。
"""

from __future__ import annotations

from pathlib import Path

from agent_world.hbm_demo.shared.prompt_paths import stories_root

_HBM_ROOT = stories_root().resolve().parent.parent  # config/stories → config → hbm_demo
# 绝对禁止写入的目录（运行期存档 + 包源码）。
_FORBIDDEN_ROOTS = tuple(
    (_HBM_ROOT / name).resolve()
    for name in ("sim", "core", "features", "http", "shared", "scripts", "config/prompts")
)


class StoryStudioSafetyError(Exception):
    """试图写入红线目录（sim/ 或包源码）。"""


def assert_safe_target(target: Path) -> Path:
    """校验 target 不在任何红线目录下，返回 resolve 后的路径；违规抛错。

    允许：config/stories/<id>/（生产）与包外临时目录（测试）。
    """
    t = Path(target).resolve()
    for root in _FORBIDDEN_ROOTS:
        if t == root or root in t.parents:
            raise StoryStudioSafetyError(
                f"story_studio 红线：禁止写入 {root}（目标 {t}）。只允许写 config/stories/<id>/。"
            )
    return t


def is_production_target(target: Path) -> bool:
    """target 是否位于 config/stories/ 下（生产落点）。"""
    t = Path(target).resolve()
    sroot = stories_root().resolve()
    return t == sroot or sroot in t.parents

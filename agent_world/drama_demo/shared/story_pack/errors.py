"""Story Pack 错误类型（dev_logs/42 §3 / dev_logs/45 §4）。

纯数据层错误，不依赖 features。validate 闸门把全部不变量违例聚合成一个
``StoryPackValidationError``（含 issue 列表），便于设计期生成工具一次性回灌修复。
"""

from __future__ import annotations

from typing import List


class StoryPackError(Exception):
    """Story Pack 加载/解析的基类错误。"""


class StoryPackValidationError(StoryPackError):
    """校验失败：聚合全部不变量违例。

    ``issues`` 为人类可读的违例描述列表（每条以 ``[V?]`` 不变量编号开头），
    设计期重生成回路据此定点回灌出问题的管理 agent。
    """

    def __init__(self, issues: List[str]) -> None:
        self.issues: List[str] = list(issues)
        joined = "\n".join(f"  - {it}" for it in self.issues)
        super().__init__(f"Story Pack 校验未通过（{len(self.issues)} 项）：\n{joined}")

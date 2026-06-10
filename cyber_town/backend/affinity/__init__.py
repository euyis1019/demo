"""好感度薄层（方案 §9）：完全独立于 agent_world 引擎的后端模块。

- ``store``    SQLite 持久化（独立 affinity.db，与 world.db 非原子——预期行为）
- ``manager``  业务逻辑：等级映射 / LLM 主路 delta / 规则法底噪 / 提示词第 6 段渲染
"""

from cyber_town.backend.affinity.manager import AffinityManager
from cyber_town.backend.affinity.store import AffinityStore

__all__ = ["AffinityManager", "AffinityStore"]

"""全局常量与配置解析。本模块不 import agent_world / openai，保持零依赖。"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).parent
REPO_ROOT = BACKEND_DIR.parent.parent
DEFAULT_SCENARIO_PATH = REPO_ROOT / "cyber_town" / "world_seed" / "scenario.yaml"

# ---- 跨层契约常量（方案 §8 / §13）------------------------------------------
PLAYER_ID = 0                 # 玩家农夫的 agent_id（固定外键，全后端统一）
TICK_SECONDS = 2.5            # 世界心跳间隔（M1 用；M0 压测后可调）
LLM_TIMEOUT_SECONDS = 20.0    # 单次 LLM 调用超时；超时该 NPC 当拍 do_nothing

# 5 段系统提示词标题（perception.build 的 segment_headers，引擎默认是 None）。
# ⚠ 段数与顺序必须与引擎 PerceptionBuilder 的 5 段语义对齐：
#   人格内核(soul) / 长期目标 / 当前状态 / 当前小目标 / 场景行为规则——不可重排。
SEGMENT_HEADERS = (
    "# 人格内核",
    "# 长期目标",
    "# 当前状态",
    "# 当前小目标",
    "# 场景行为规则",
)


def load_dotenv_into_environ(env_path: Optional[Path] = None) -> None:
    """把 ``backend/.env`` 的 KEY=VALUE 写进 os.environ（已有的环境变量优先）。

    不引入 python-dotenv 依赖——与 run_demo._load_dotenv_into_environ 同款。
    """
    candidate = env_path or (BACKEND_DIR / ".env")
    if not candidate.exists():
        return
    for raw in candidate.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class LLMConfig:
    """一次性解析完的 LLM 接入配置（对 llm_client 工厂的输入契约）。"""

    base_url: str
    model: str
    # repr=False：防止 print/log/调试时把 key 带出去（审查 CONFIG-1）
    api_key: str = field(repr=False)
    temperature: float = 0.8
    max_tokens: int = 400
    timeout: float = LLM_TIMEOUT_SECONDS


def resolve_llm_config(scenario_llm: Dict[str, Any]) -> LLMConfig:
    """按优先级解析 LLM 配置：yaml 字面量 key > api_key_env 环境变量。

    Raises:
        RuntimeError: 找不到任何 key 时（提示用户写 .env）。
    """
    load_dotenv_into_environ()

    literal = scenario_llm.get("api_key")
    if literal and not str(literal).startswith("$"):
        api_key = str(literal)
    else:
        env_name = scenario_llm.get("api_key_env", "LLM_API_KEY")
        api_key = os.environ.get(env_name) or os.environ.get("LLM_API_KEY") or ""
    if not api_key:
        raise RuntimeError(
            "未找到 LLM key：请往 cyber_town/backend/.env 写一行 "
            "LLM_API_KEY=sk-...（该文件已 gitignore）。"
        )

    return LLMConfig(
        base_url=str(scenario_llm.get("base_url", "https://api.deepseek.com")),
        model=str(scenario_llm.get("model", "deepseek-v4-flash")),
        api_key=api_key,
        temperature=float(scenario_llm.get("temperature", 0.8)),
        max_tokens=int(scenario_llm.get("max_tokens", 400)),
        timeout=float(scenario_llm.get("timeout", LLM_TIMEOUT_SECONDS)),
    )

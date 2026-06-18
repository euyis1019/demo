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

# 5 段系统提示词标题已移至 prompts/segments.py（W6：提示词集中管理）


def day_phase(hhmm: str) -> str:
    """世界时间 HH:MM → 时段标签（焐心小镇支柱2：作息节律的单一真相源）。

    清晨 5-10 / 晌午 11-15 / 傍晚 16-19 / 夜里 20-4。仅作为【事实】供 NPC
    感知与前端显示，不强制任何作息——NPC 自主按 soul 决定去留。
    """
    try:
        hour = int(str(hhmm).split(":")[0])
    except (ValueError, IndexError, AttributeError):
        return ""
    if 5 <= hour <= 10:
        return "清晨"
    if 11 <= hour <= 15:
        return "晌午"
    if 16 <= hour <= 19:
        return "傍晚"
    return "夜里"


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
    # None = 不传 max_tokens（用 API 默认上限）——W6 用户拍板放开输出预算，
    # 防 reasoning 模型（deepseek-v4-flash）思维链挤占答案额度导致截断；
    # 需要限制时在 scenario.yaml 的 llm 段显式写 max_tokens
    max_tokens: Optional[int] = None
    # W8：NPC 拍内决策禁用思维链（DeepSeek thinking.disabled）——实测 v4-flash
    # 带思维链时 tool_calls 产出不稳定（答话写进思维链不调工具→被当独白丢弃，
    # 即「不回复」主根因），且时延 4.2s→2.7s。导演元决策不受此开关影响。
    # 换非 DeepSeek 网关时若不识别该参数，在 scenario.yaml 设 disable_thinking: false
    disable_thinking: bool = True
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

    raw_max = scenario_llm.get("max_tokens")
    return LLMConfig(
        base_url=str(scenario_llm.get("base_url", "https://api.deepseek.com")),
        model=str(scenario_llm.get("model", "deepseek-v4-flash")),
        api_key=api_key,
        temperature=float(scenario_llm.get("temperature", 0.8)),
        max_tokens=int(raw_max) if raw_max else None,
        disable_thinking=bool(scenario_llm.get("disable_thinking", True)),
        timeout=float(scenario_llm.get("timeout", LLM_TIMEOUT_SECONDS)),
    )

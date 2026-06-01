"""真实 LLM 客户端适配器（仅 CLI generate 用；测试用 fake，不触此文件）。

把 openai SDK 包成 base_agent 期望的 LLMClient（(system, user) -> str）。api key 从环境变量取，
**不 import core.runner.kernel**（保持 story_studio 红线：不引运行期）。
"""

from __future__ import annotations

import os
from typing import Any, Dict

from agent_world.drama_demo.tools.story_studio.base_agent import LLMClient


def _resolve_api_key(llm_cfg: Dict[str, Any]) -> str:
    env_name = llm_cfg.get("api_key_env", "DMXAPI_KEY")
    key = os.environ.get(str(env_name), "") or str(llm_cfg.get("api_key", "") or "")
    if not key:
        raise RuntimeError(f"未找到 LLM API key（环境变量 {env_name} 为空）")
    return key


def make_llm_client(llm_cfg: Dict[str, Any] | None = None, *, temperature: float = 0.4) -> LLMClient:
    """构造一个 DeepSeek/OpenAI 兼容的同步 LLMClient。"""
    from openai import OpenAI

    cfg = dict(llm_cfg or {})
    client = OpenAI(
        api_key=_resolve_api_key(cfg),
        base_url=cfg.get("base_url", "https://api.deepseek.com/v1"),
    )
    model = cfg.get("model", "deepseek-chat")

    def _call(system: str, user: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""

    return _call

"""call_llm_json —— JSON 输出的轻量 LLM 调用（导演等元决策用，fail-soft）。

W6 注：原 directors/base.py，随提示词集中与分包重组移入 llm/。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.S)


async def call_llm_json(
    client: Any,
    model: str,
    system: str,
    user: str,
    timeout: float = 30.0,
    max_tokens: Optional[int] = None,   # W6 用户拍板：导演不限输出预算（None=不传）
) -> Optional[Dict[str, Any]]:
    """调一次 LLM 并解析 JSON 对象；任何失败返回 None（调用方自行降级）。

    timeout 经 per-request 透传给 SDK（审查 W6-T1：共享 AsyncOpenAI 构造层是
    20s，不透传的话单次尝试 20s 即被切断 + SDK 静默重试白烧两次额度）；
    外层 wait_for 只作最终兜底。
    """
    try:
        kwargs: Dict[str, Any] = dict(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,           # 元决策要稳，低温
            # DeepSeek 兼容 OpenAI 的 JSON 模式，强约束输出为合法 JSON
            response_format={"type": "json_object"},
            # 覆盖 client 构造层 timeout（NPC 的 20s 变速拍对策不适用于后台导演）
            timeout=timeout,
        )
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        resp = await asyncio.wait_for(
            client.chat.completions.create(**kwargs), timeout=timeout + 10,
        )
        text = (resp.choices[0].message.content or "").strip()
        m = _JSON_RE.search(text)
        if not m:
            return None
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001 — 导演失败绝不阻断世界
        log.warning("导演 LLM 调用失败：%s", exc)
        return None

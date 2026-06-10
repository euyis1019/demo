"""导演共用工具：JSON 输出的轻量 LLM 调用（fail-soft）。"""

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
    timeout: float = 20.0,
    max_tokens: int = 1200,   # deepseek-v4-flash 的思维链与答案共享额度，给足防截断
) -> Optional[Dict[str, Any]]:
    """调一次 LLM 并解析 JSON 对象；任何失败返回 None（调用方自行降级）。"""
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,           # 元决策要稳，低温
                max_tokens=max_tokens,
                # DeepSeek 兼容 OpenAI 的 JSON 模式，强约束输出为合法 JSON
                response_format={"type": "json_object"},
            ),
            timeout=timeout,
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

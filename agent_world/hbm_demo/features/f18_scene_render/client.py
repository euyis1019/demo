"""文生图客户端。P0 用 Pollinations.ai（免费、免密钥、URL 直出图）。

只依赖标准库 urllib，避免新增第三方依赖。提供同步 fetch 与 async 包装
（async 用 asyncio.to_thread，便于 P1 接入异步 tick 循环而不阻塞事件循环）。
"""

from __future__ import annotations

import asyncio
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

_POLLINATIONS_BASE = "https://image.pollinations.ai/prompt/"


def _ssl_context() -> ssl.SSLContext:
    """用 certifi 根证书构建上下文，规避 macOS 自带 Python 缺根证书问题。"""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


_SSL_CTX = _ssl_context()


@dataclass
class ImageResult:
    ok: bool
    image_bytes: Optional[bytes]
    mime: str
    url: str
    error: Optional[str] = None


def build_pollinations_url(
    prompt: str,
    *,
    width: int,
    height: int,
    seed: int,
    model: str,
    nologo: bool,
) -> str:
    encoded = urllib.parse.quote(prompt, safe="")
    query = urllib.parse.urlencode(
        {
            "width": width,
            "height": height,
            "seed": seed,
            "model": model,
            "nologo": "true" if nologo else "false",
        }
    )
    return f"{_POLLINATIONS_BASE}{encoded}?{query}"


def fetch_image_sync(
    prompt: str,
    *,
    width: int,
    height: int,
    seed: int,
    model: str,
    nologo: bool,
    timeout_sec: float,
) -> ImageResult:
    url = build_pollinations_url(
        prompt, width=width, height=height, seed=seed, model=model, nologo=nologo
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hbm-demo-f18/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_sec, context=_SSL_CTX) as resp:
            data = resp.read()
            mime = resp.headers.get("Content-Type", "image/jpeg")
        if not data:
            return ImageResult(False, None, mime, url, "empty response")
        return ImageResult(True, data, mime, url)
    except Exception as exc:  # 网络/超时统一兜底，渲染失败不应拖垮世界逻辑
        return ImageResult(False, None, "image/jpeg", url, str(exc))


async def fetch_image(
    prompt: str,
    *,
    width: int,
    height: int,
    seed: int,
    model: str,
    nologo: bool,
    timeout_sec: float,
) -> ImageResult:
    return await asyncio.to_thread(
        fetch_image_sync,
        prompt,
        width=width,
        height=height,
        seed=seed,
        model=model,
        nologo=nologo,
        timeout_sec=timeout_sec,
    )

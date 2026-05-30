"""文生图 / 图生图客户端 —— Doubao-Seedream-4.5（火山 Ark）。

只依赖标准库 urllib（+ certifi 证书），避免新增第三方依赖。
- 无 ref_image_url → 文生图(t2i)，出新锚定帧。
- 有 ref_image_url → 图生图(img2img)，以上一帧为参考锁住角色/场景、只改动作。
返回的 ImageResult 带回图片字节与 Seedream 返回的 url（作为下一帧的参考）。
"""

from __future__ import annotations

import asyncio
import json
import ssl
import urllib.request
from dataclasses import dataclass
from typing import Optional


def _ssl_context() -> ssl.SSLContext:
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
    url: str  # Seedream 返回的图片 url（用作下一帧 img2img 的参考）
    error: Optional[str] = None


def _http_json(url: str, *, payload: dict, api_key: str, timeout: float) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_bytes(url: str, *, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "hbm-demo-f18/2.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return resp.read()


def generate_sync(
    prompt: str,
    *,
    endpoint: str,
    model: str,
    api_key: str,
    size: str,
    watermark: bool,
    timeout_sec: float,
    seed: Optional[int] = None,
    ref_image_url: Optional[str] = None,
) -> ImageResult:
    if not api_key:
        return ImageResult(False, None, "image/jpeg", "", "missing ARK_API_KEY")
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "response_format": "url",
        "watermark": watermark,
    }
    if seed is not None:
        payload["seed"] = int(seed)
    if ref_image_url:
        payload["image"] = ref_image_url
    try:
        data = _http_json(endpoint, payload=payload, api_key=api_key, timeout=timeout_sec)
        items = data.get("data") or []
        url = items[0].get("url") if items else None
        if not url:
            return ImageResult(False, None, "image/jpeg", "", str(data.get("error") or "no url"))
        img = _http_get_bytes(url, timeout=timeout_sec)
        if not img:
            return ImageResult(False, None, "image/jpeg", url, "empty image")
        return ImageResult(True, img, "image/jpeg", url)
    except Exception as exc:  # 网络/超时统一兜底，绝不拖垮世界逻辑
        return ImageResult(False, None, "image/jpeg", "", str(exc))


async def generate(
    prompt: str,
    *,
    endpoint: str,
    model: str,
    api_key: str,
    size: str,
    watermark: bool,
    timeout_sec: float,
    seed: Optional[int] = None,
    ref_image_url: Optional[str] = None,
) -> ImageResult:
    return await asyncio.to_thread(
        generate_sync,
        prompt,
        endpoint=endpoint,
        model=model,
        api_key=api_key,
        size=size,
        watermark=watermark,
        timeout_sec=timeout_sec,
        seed=seed,
        ref_image_url=ref_image_url,
    )

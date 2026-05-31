"""文生图客户端 —— Doubao-Seedream 4.5（火山 Ark）。

只依赖标准库 urllib（+ certifi 证书）。key 从环境变量 ARK_API_KEY 读，缺失即抛 ImageKeyMissing
（要求用户配置）。供 Artist 管理 agent 出图用。
"""

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ARK_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
ARK_T2I_MODEL = os.environ.get("ARK_T2I_MODEL", "doubao-seedream-4-5-251128")


class ImageKeyMissing(Exception):
    """未配置文生图 API key。"""


class ImageGenError(Exception):
    """出图失败（HTTP / 解析 / 下载错误）。"""


def require_api_key() -> str:
    key = (os.environ.get("ARK_API_KEY") or "").strip()
    if not key:
        raise ImageKeyMissing(
            "未配置文生图 API key。请在 agent_world/hbm_demo/.env 写入 ARK_API_KEY=ark-...（火山 Ark），"
            "或导出环境变量 ARK_API_KEY 后重试。"
        )
    return key


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


_SSL_CTX = _ssl_context()


def seedream_size(size_hint: str) -> str:
    """把清单里的建议尺寸（如 "1920×1080" / "1024×1536"）映射到 Seedream 支持的 2K 尺寸。"""
    nums = re.findall(r"\d+", str(size_hint or ""))
    if len(nums) != 2:
        return "2560x1440"
    w, h = int(nums[0]), int(nums[1])
    if h > w:
        return "1728x2304"   # 竖（立绘 3:4）
    if w > h:
        return "2560x1440"   # 横（封面/场景 16:9）
    return "2048x2048"       # 方


@dataclass
class ImageResult:
    ok: bool
    path: Optional[Path]
    url: str = ""
    error: Optional[str] = None


def generate_image(prompt: str, *, size_hint: str, out_path: Path, watermark: bool = False,
                   timeout_sec: float = 180.0) -> ImageResult:
    """调 Seedream 出一张图，下载并写入 out_path。返回 ImageResult。"""
    key = require_api_key()  # 缺 key 直接抛 ImageKeyMissing
    payload = {
        "model": ARK_T2I_MODEL,
        "prompt": prompt,
        "size": seedream_size(size_hint),
        "response_format": "url",
        "watermark": watermark,
    }
    req = urllib.request.Request(
        ARK_ENDPOINT, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec, context=_SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        return ImageResult(False, None, error=f"HTTP {exc.code}: {exc.read().decode()[:200]}")
    except Exception as exc:  # noqa: BLE001
        return ImageResult(False, None, error=f"请求失败：{exc}")

    items = data.get("data") or []
    url = items[0].get("url") if items else ""
    if not url:
        return ImageResult(False, None, error=f"返回无 url：{str(data)[:200]}")

    try:
        get = urllib.request.Request(url, headers={"User-Agent": "hbm-demo-artist/1.0"})
        with urllib.request.urlopen(get, timeout=timeout_sec, context=_SSL_CTX) as r2:
            img = r2.read()
    except Exception as exc:  # noqa: BLE001
        return ImageResult(False, None, url=url, error=f"下载失败：{exc}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(img)
    return ImageResult(True, out_path, url=url)

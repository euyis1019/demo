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
# 主模型「额度不够」(429) 时自动切到的备用模型。默认用 doubao-seedream-4-0-250828——这是经实测**真实存在
# 且可调用**的 ARK 文生图模型 id（旧默认 doubao-seedream-5-0-lite 实为 404 NotFound·并非有效 id，导致主模型
# 429 后备用也跟着挂）。账号若开通了别的图模型，设环境变量 ARK_T2I_MODEL / ARK_T2I_FALLBACK_MODEL 覆盖即可。
ARK_T2I_FALLBACK_MODEL = os.environ.get("ARK_T2I_FALLBACK_MODEL", "doubao-seedream-4-0-250828")

# 判定「额度/余额不够」的信号：HTTP 429，或错误体里出现这些词（中英）。命中即切备用模型重试。
_QUOTA_HINTS = (
    "quota", "balance", "insufficient", "exceeded", "exceed", "limit reached",
    "arrearage", "overdue", "额度", "余额", "欠费", "配额", "超出", "用尽", "不足",
)


class ImageKeyMissing(Exception):
    """未配置文生图 API key。"""


class ImageGenError(Exception):
    """出图失败（HTTP / 解析 / 下载错误）。"""


def require_api_key() -> str:
    key = (os.environ.get("ARK_API_KEY") or "").strip()
    if not key:
        raise ImageKeyMissing(
            "未配置文生图 API key。请在 agent_world/drama_demo/.env 写入 ARK_API_KEY=ark-...（火山 Ark），"
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


def _is_quota_error(code: int, body: str) -> bool:
    """是不是「额度/余额不够」类错误——HTTP 429，或错误体含额度相关字样。"""
    if code == 429:
        return True
    b = (body or "").lower()
    return any(h in b for h in _QUOTA_HINTS)


def _post_generation(model: str, payload: dict, key: str, timeout_sec: float):
    """发一次出图请求。成功返回 (data, None)；失败返回 (None, (http_code, body))（http_code=0 表非 HTTP 错误）。"""
    body = {**payload, "model": model}
    req = urllib.request.Request(
        ARK_ENDPOINT, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec, context=_SSL_CTX) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        return None, (exc.code, exc.read().decode()[:300])
    except Exception as exc:  # noqa: BLE001
        return None, (0, f"请求失败：{exc}")


def generate_image(prompt: str, *, size_hint: str, out_path: Path, watermark: bool = False,
                   negative_prompt: str = "", seed: Optional[int] = None,
                   ref_image_url: str = "", timeout_sec: float = 180.0) -> ImageResult:
    """调 Seedream 出一张图，下载并写入 out_path。返回 ImageResult。

    negative_prompt：负向约束（如场景图的「无人物」），非空时透传给模型，从机制上排除不想要的内容。
    seed：固定随机种子——同一角色的基础立绘与各情绪变体用同一 seed，锚定同一人物形象保持一致。
    ref_image_url：参考图 URL（图生图 img2img，锁住角色/构图只改局部，如情绪表情）；为空则纯文生图。
    ★主模型额度不够(HTTP 429/余额不足)时，自动切到备用模型 ARK_T2I_FALLBACK_MODEL 重试一次。
    """
    key = require_api_key()  # 缺 key 直接抛 ImageKeyMissing
    payload = {
        "prompt": prompt,
        "size": seedream_size(size_hint),
        "response_format": "url",
        "watermark": watermark,
    }
    if negative_prompt and negative_prompt.strip():
        payload["negative_prompt"] = negative_prompt.strip()
    if seed is not None:
        payload["seed"] = int(seed)
    if ref_image_url:
        payload["image"] = ref_image_url

    data, err = _post_generation(ARK_T2I_MODEL, payload, key, timeout_sec)
    # 额度不够 → 自动切备用模型重试一次（Doubao-Seedream-5.0-lite）。
    if err is not None and _is_quota_error(err[0], err[1]) \
            and ARK_T2I_FALLBACK_MODEL and ARK_T2I_FALLBACK_MODEL != ARK_T2I_MODEL:
        print(f"[出图] 主模型 {ARK_T2I_MODEL} 额度不够({err[0]})，切到备用模型 {ARK_T2I_FALLBACK_MODEL} 重试…", flush=True)
        data, err = _post_generation(ARK_T2I_FALLBACK_MODEL, payload, key, timeout_sec)
    if err is not None:
        code, body = err
        return ImageResult(False, None, error=(f"HTTP {code}: {body[:200]}" if code else str(body)))

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

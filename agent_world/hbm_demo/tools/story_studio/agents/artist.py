"""Artist 管理 agent（生成期·美术）：把"故事需要哪些图"变成真实图片资源。

职责：
1. 读 Story Pack 推导出的图片需求清单（asset_specs，需求/数量由设计 agent 经 Story Pack 给出）；
2. 逐张调文生图模型（Seedream）出图，落 config/stories/<id>/assets/；
3. **自审**每张是否合格（有效图 + 尺寸正常 + 可选的视觉语义复核），不合格则重画；
4. **查数量是否足够**：是否每张需求都已就位、够不够把故事跑起来，给出缺口清单。

视觉语义复核（_vision_review）走 Ark 视觉模型，best-effort：模型不可用时降级为基础校验。
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent_world.hbm_demo.tools.story_studio.asset_manifest import AssetSpec, asset_specs
from agent_world.hbm_demo.tools.story_studio.image_client import (
    ImageKeyMissing,
    generate_image,
    require_api_key,
)

_MIN_BYTES = 8 * 1024  # 小于这个多半是错误占位/空图


def _valid_image(path: Path) -> Tuple[bool, str]:
    """基础自审：文件存在、非空、是 PNG/JPEG/WebP、尺寸不至于过小。"""
    if not path.is_file():
        return False, "文件不存在"
    data = path.read_bytes()
    if len(data) < _MIN_BYTES:
        return False, f"图过小（{len(data)}B），疑似无效"
    head = data[:12]
    if head.startswith(b"\xff\xd8"):
        return True, "JPEG 有效"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return True, "PNG 有效"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return True, "WebP 有效"
    return False, "非已知图片格式"


def _vision_review(prompt: str, label: str, image_url: str,
                   question: Optional[str] = None) -> Optional[Tuple[bool, str]]:
    """可选的视觉语义复核：让 Ark 视觉模型看图、判断是否符合需求。

    默认**关闭**（能生成即可）——仅当显式设置 ARK_VISION_MODEL=<视觉模型id> 时才启用；
    模型不可用/出错→返回 None（跳过，交给基础校验）。
    question：自定义判定问题（如场景图专门检测「是否混进人物」）；缺省走通用「是否符合需求」。
    """
    model = (os.environ.get("ARK_VISION_MODEL") or "").strip()
    if not model or not image_url:
        return None
    ask = question or (
        f"这张图是为「{label}」生成的，原始需求：{prompt}\n"
        "请判断它是否大体符合需求（题材/内容/构图对就算合格，不必苛求细节）。"
        "只输出 JSON：{\"ok\": true或false, \"reason\": \"一句中文\"}"
    )
    try:
        key = require_api_key()
        try:
            import certifi

            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:  # noqa: BLE001
            ctx = ssl.create_default_context()
        body = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": ask},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }],
            "temperature": 0,
        }
        req = urllib.request.Request(
            "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
            data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=90, context=ctx) as resp:
            data = json.loads(resp.read().decode())
        txt = data["choices"][0]["message"]["content"]
        import re

        m = re.search(r"\{.*\}", txt, re.S)
        if not m:
            return None
        d = json.loads(m.group(0))
        return bool(d.get("ok")), str(d.get("reason") or "")
    except Exception:  # noqa: BLE001
        return None  # 视觉模型不可用 → 降级（交给基础校验）


@dataclass
class ArtItem:
    spec: AssetSpec
    status: str            # present | ok | reject | failed
    note: str = ""
    url: str = ""


@dataclass
class ArtReport:
    items: List[ArtItem] = field(default_factory=list)
    required: int = 0
    present: int = 0
    missing: List[str] = field(default_factory=list)

    @property
    def enough(self) -> bool:
        return not self.missing


class Artist:
    """美术管理 agent：出图 + 自审 + 查数量是否足够。"""

    def __init__(self, *, review: bool = True, max_retry: int = 1) -> None:
        self.review = review
        self.max_retry = max_retry

    def review_one(self, spec: AssetSpec, path: Path, url: str) -> Tuple[bool, str]:
        ok, why = _valid_image(path)
        if not ok:
            return False, why
        # 场景图专门检测「是否混进人物」（设了 ARK_VISION_MODEL 才生效），命中即判不合格重画。
        question = None
        if spec.kind == "scene":
            question = (
                f"这是一张「{spec.label}」的空镜背景图，要求画面里【绝对不能出现任何人物】"
                "（人、人脸、人影、剪影、背影都不允许）。请仔细看：图里出现人物了吗？"
                "只输出 JSON：{\"ok\": true(无人物/合格) 或 false(有人物/不合格), \"reason\": \"一句中文\"}"
            )
        v = _vision_review(spec.prompt, spec.label, url, question=question) if url else None
        if v is not None:
            return v[0], ("视觉复核：" + v[1])
        return True, "基础自审通过（" + why + "）"

    def _produce_one(self, spec: AssetSpec, asset_dir: Path, only_missing: bool,
                     ref_image_url: str = "") -> ArtItem:
        """出一张图（含重画自审）。供串行/并发两种调度共用。
        ref_image_url：情绪变体的参考图 URL（图生图锁住相貌一致）；为空走纯文生图。"""
        out = asset_dir / spec.rel_path
        if only_missing and _valid_image(out)[0]:
            return ArtItem(spec, "present", "已存在")
        verdict, note, url = "failed", "", ""
        for _attempt in range(self.max_retry + 1):
            res = generate_image(
                spec.prompt, size_hint=spec.size, out_path=out,
                negative_prompt=spec.negative, seed=spec.seed,
                ref_image_url=ref_image_url,
            )
            url = res.url
            if not res.ok:
                verdict, note = "failed", res.error or "出图失败"
                break
            if not self.review:
                verdict, note = "ok", "未审核"
                break
            ok, why = self.review_one(spec, out, url)
            if ok:
                verdict, note = "ok", why
                break
            verdict, note = "reject", why  # 自审不过 → 重画
        return ArtItem(spec, verdict, note, url)

    def _run_batch(self, specs: List[AssetSpec], asset_dir: Path, only_missing: bool,
                   ref_urls: Optional[Dict[str, str]] = None) -> List[ArtItem]:
        """并发出一批图。ref_urls：rel_path→参考图 URL（情绪变体用各自基础立绘的 URL 做图生图）。"""
        if not specs:
            return []
        ref_urls = ref_urls or {}

        def one(s: AssetSpec) -> ArtItem:
            return self._produce_one(s, asset_dir, only_missing,
                                     ref_image_url=ref_urls.get(s.ref_rel_path, ""))

        workers = max(1, int(os.environ.get("ARK_T2I_CONCURRENCY", "5")))
        if workers <= 1 or len(specs) <= 1:
            return [one(s) for s in specs]
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(one, specs))

    def run(self, pack: Any, asset_dir: Path, *, only_missing: bool = True,
            limit: Optional[int] = None) -> ArtReport:
        """出齐 Story Pack 需要的全部图片（默认只补缺的）。limit 仅出前 N 张（调试用）。

        两阶段并发：先出基础图（封面/场景/基础立绘），再以各基础立绘的 URL 为参考做图生图出情绪变体，
        锁住同一角色相貌一致。并发（ARK_T2I_CONCURRENCY，默认 5）把情绪变体带来的数量膨胀压回可接受墙钟。
        """
        require_api_key()  # 缺 key 早抛，提示配置
        specs = asset_specs(pack)
        report = ArtReport(required=len(specs))
        todo = specs[:limit] if limit else specs
        base_specs = [s for s in todo if not s.ref_rel_path]
        variant_specs = [s for s in todo if s.ref_rel_path]

        base_items = self._run_batch(base_specs, asset_dir, only_missing)
        # 收集基础立绘的新鲜 URL，供情绪变体图生图参考（基础图被跳过/失败则该角色变体回退纯文生图）
        ref_urls = {it.spec.rel_path: it.url for it in base_items if it.url}
        variant_items = self._run_batch(variant_specs, asset_dir, only_missing, ref_urls=ref_urls)
        report.items = base_items + variant_items
        # 查数量是否足够（所有需求是否就位）
        report.missing = [s.label for s in specs if not _valid_image(asset_dir / s.rel_path)[0]]
        report.present = report.required - len(report.missing)
        return report

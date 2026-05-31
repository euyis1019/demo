"""素材清单：从一份 Story Pack 推导"需要哪些图片"+ 每张的文生图提示词（确定性模板，纯离线）。

两种用法：
- asset_specs(pack)：返回结构化的图片需求清单（kind/路径/尺寸/提示词），供 Artist agent 出图。
- render_asset_manifest / write_asset_manifest：渲染成人读的 ASSETS_TODO.txt。

「需要多少张、每张要画什么」由剧情规划/设计的产出（Story Pack：地点→背景、角色→立绘、+封面）确定，
即设计 agent 通过 Story Pack 把需求交给 Artist。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from agent_world.hbm_demo.shared.prompt_paths import story_dir
from agent_world.hbm_demo.shared.story_pack import StoryPack
from agent_world.hbm_demo.tools.story_studio.safety import assert_safe_target

MANIFEST_FILENAME = "ASSETS_TODO.txt"

_STYLE = "电影感数字绘景，写实柔和光照，高细节，氛围统一；全系列保持同一画风与色调以便拼接成完整世界。"


@dataclass(frozen=True)
class AssetSpec:
    """一张需要的图片：kind=cover|scene|portrait；rel_path 相对 story_dir；size 建议尺寸；prompt 文生图提示词。"""

    kind: str
    key: str          # 标识（cover / place_id / agent_id）
    label: str        # 人读标签
    rel_path: str     # 相对 config/stories/<id>/ 的落点
    size: str         # 建议尺寸，如 "1920×1080"
    prompt: str       # 可直接喂文生图模型的提示词


def _first_sentence(text: str, limit: int = 60) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    for sep in ("。", "！", "？", ".", "!", "?"):
        if sep in t:
            t = t.split(sep)[0]
            break
    return t[:limit]


def asset_specs(pack: StoryPack) -> List[AssetSpec]:
    """从 Story Pack 推导全部需要的图片需求（封面 + 每个地点背景 + 每个非玩家角色立绘）。"""
    meta = pack.meta or {}
    title = meta.get("title") or pack.story_id
    specs: List[AssetSpec] = []

    # 1) 封面
    synopsis = _first_sentence(meta.get("synopsis") or meta.get("premise") or "", 80)
    specs.append(AssetSpec(
        kind="cover", key="cover", label=f"封面图《{title}》",
        rel_path="assets/cover.png", size="1920×1080",
        prompt=f"游戏封面，主题《{title}》。{synopsis}。史诗感构图，标题留白区域，{_STYLE}",
    ))

    # 2) 地点背景（每个 place 一张，空镜无人物）
    for p in pack.places.get("places", []) or []:
        attrs = p.get("attrs") or {}
        summary = _first_sentence(attrs.get("summary") or p["place_id"], 80)
        hint = _first_sentence(attrs.get("behavior_hint") or "", 50)
        mood = f"氛围：{hint}。" if hint else ""
        specs.append(AssetSpec(
            kind="scene", key=str(p["place_id"]), label=f"场景背景：{p['place_id']}",
            rel_path=f"assets/places/{p['place_id']}.png", size="1920×1080",
            prompt=f"室内/室外场景「{summary}」。{mood}空镜，无人物，可作对话背景，{_STYLE}",
        ))

    # 3) 角色立绘（每个非玩家 agent 一张，半身）
    for a in pack.agents.get("agents", []) or []:
        if int(a.get("agent_id", -1)) == 0:
            continue
        name = a.get("name", f"agent_{a['agent_id']}")
        persona = _first_sentence(a.get("soul") or "", 70)
        role = a.get("role") or ""
        role_txt = f"（{role}）" if role else ""
        specs.append(AssetSpec(
            kind="portrait", key=str(a["agent_id"]), label=f"角色立绘：{name}{role_txt}",
            rel_path=f"assets/avatars/agent_{a['agent_id']}.png", size="1024×1536",
            prompt=f"人物半身立绘，{name}{role_txt}。性格气质：{persona}。"
                   f"正面或四分之三侧面，干净纯色背景便于抠图，{_STYLE}",
        ))

    return specs


def render_asset_manifest(pack: StoryPack) -> str:
    title = (pack.meta or {}).get("title") or pack.story_id
    specs = asset_specs(pack)
    lines: List[str] = [
        f"# 《{title}》图片素材清单（放入 config/stories/{pack.story_id}/assets/）",
        "",
        "说明：每条给了建议文件名、尺寸和可直接喂文生图模型的提示词。",
        f"统一画风要求：{_STYLE}",
        "",
    ]
    for i, s in enumerate(specs, 1):
        orient = "竖，半身" if s.kind == "portrait" else "横，无人物" if s.kind == "scene" else "横"
        lines.append(f"[{i}] {s.label}  → {s.rel_path}  （{s.size}，{orient}）")
        lines.append(f"    提示词：{s.prompt}")
        if s.kind == "portrait":
            lines.append(f"    情绪变体(可选)：{s.rel_path[:-4]}_{{angry,happy,sad,anxious,confident}}.png"
                         "（前端按情绪切换，缺则回退基础立绘）")
        lines.append("")
    lines.append(f"# 共需 {len(specs)} 张图片。出好后按上面文件名放入 assets/ 即可。")
    return "\n".join(lines)


def write_asset_manifest(pack: StoryPack, target_dir: Optional[Path] = None) -> Path:
    """渲染清单并写到 <story_dir>/ASSETS_TODO.txt（过安全红线）。返回文件路径。"""
    target = assert_safe_target(Path(target_dir) if target_dir is not None else story_dir(pack.story_id))
    target.mkdir(parents=True, exist_ok=True)
    path = target / MANIFEST_FILENAME
    path.write_text(render_asset_manifest(pack), encoding="utf-8")
    return path

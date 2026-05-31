"""素材清单生成器（G5，按用户要求：不自动出图，而是产 txt 清单 + 详细提示词，用户自备素材）。

从一份 Story Pack 推导"需要哪些图片"，并为每张给出**足够详细、可直接喂文生图模型**的提示词
（确定性模板，纯离线，无 LLM）。落 config/stories/<id>/ASSETS_TODO.txt。用户照单出图，放进 assets/。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from agent_world.hbm_demo.shared.prompt_paths import story_dir
from agent_world.hbm_demo.shared.story_pack import StoryPack
from agent_world.hbm_demo.tools.story_studio.safety import assert_safe_target

MANIFEST_FILENAME = "ASSETS_TODO.txt"

_STYLE = "电影感数字绘景，写实柔和光照，高细节，氛围统一；全系列保持同一画风与色调以便拼接成完整世界。"


def _first_sentence(text: str, limit: int = 60) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    for sep in ("。", "！", "？", ".", "!", "?"):
        if sep in t:
            t = t.split(sep)[0]
            break
    return t[:limit]


def render_asset_manifest(pack: StoryPack) -> str:
    meta = pack.meta or {}
    title = meta.get("title") or pack.story_id
    lines: List[str] = []
    lines.append(f"# 《{title}》图片素材清单（请自备以下图片，放入 config/stories/{pack.story_id}/assets/）")
    lines.append("")
    lines.append("说明：每条给了建议文件名、尺寸和可直接喂文生图模型的提示词。")
    lines.append(f"统一画风要求：{_STYLE}")
    lines.append("")

    n = 0
    # 1) 封面
    n += 1
    synopsis = _first_sentence(meta.get("synopsis") or "", 80)
    lines.append(f"[{n}] 封面图  → assets/cover.png  （1920×1080，横）")
    lines.append(f"    提示词：游戏封面，主题《{title}》。{synopsis}。"
                 f"史诗感构图，标题留白区域，{_STYLE}")
    lines.append("")

    # 2) 地点背景（每个 place 一张）
    for p in pack.places.get("places", []) or []:
        n += 1
        attrs = p.get("attrs") or {}
        summary = _first_sentence(attrs.get("summary") or p["place_id"], 80)
        hint = _first_sentence(attrs.get("behavior_hint") or "", 50)
        mood = f"氛围：{hint}。" if hint else ""
        lines.append(f"[{n}] 场景背景：{p['place_id']}  → assets/places/{p['place_id']}.png  （1920×1080，横，无人物）")
        lines.append(f"    提示词：室内/室外场景「{summary}」。{mood}空镜，无人物，可作对话背景，{_STYLE}")
        lines.append("")

    # 3) 角色立绘（每个非玩家 agent 一张）
    for a in pack.agents.get("agents", []) or []:
        if int(a.get("agent_id", -1)) == 0:
            continue  # 玩家无需立绘
        n += 1
        name = a.get("name", f"agent_{a['agent_id']}")
        persona = _first_sentence(a.get("soul") or "", 70)
        role = a.get("role") or ""
        role_txt = f"（{role}）" if role else ""
        lines.append(f"[{n}] 角色立绘：{name}{role_txt}  → assets/avatars/agent_{a['agent_id']}.png  （1024×1536，竖，半身）")
        lines.append(f"    提示词：人物半身立绘，{name}{role_txt}。性格气质：{persona}。"
                     f"正面或四分之三侧面，干净纯色背景便于抠图，{_STYLE}")
        lines.append("")

    lines.append(f"# 共需 {n} 张图片。出好后按上面文件名放入 assets/ 即可。")
    return "\n".join(lines)


def write_asset_manifest(pack: StoryPack, target_dir: Optional[Path] = None) -> Path:
    """渲染清单并写到 <story_dir>/ASSETS_TODO.txt（过安全红线）。返回文件路径。"""
    target = assert_safe_target(Path(target_dir) if target_dir is not None else story_dir(pack.story_id))
    target.mkdir(parents=True, exist_ok=True)
    path = target / MANIFEST_FILENAME
    path.write_text(render_asset_manifest(pack), encoding="utf-8")
    return path

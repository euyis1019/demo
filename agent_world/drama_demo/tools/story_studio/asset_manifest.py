"""素材清单：从一份 Story Pack 推导"需要哪些图片"+ 每张的文生图提示词（确定性模板，纯离线）。

两种用法：
- asset_specs(pack)：返回结构化的图片需求清单（kind/路径/尺寸/提示词），供 Artist agent 出图。
- render_asset_manifest / write_asset_manifest：渲染成人读的 ASSETS_TODO.txt。

「需要多少张、每张要画什么」由剧情规划/设计的产出（Story Pack：地点→背景、角色→立绘、+封面）确定，
即设计 agent 通过 Story Pack 把需求交给 Artist。
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from agent_world.drama_demo.shared.emotion import EMOTIONS
from agent_world.drama_demo.shared.prompt_paths import story_dir
from agent_world.drama_demo.shared.story_pack import StoryPack
from agent_world.drama_demo.tools.story_studio.safety import assert_safe_target

MANIFEST_FILENAME = "ASSETS_TODO.txt"

# 各情绪对应的表情/姿态描述，叠加在基础人设上生成「分情绪立绘」（前端按情绪切换）。
# neutral 用基础立绘本身，不单独出图。
_EMOTION_FACE = {
    "happy": "此刻情绪【开心愉悦】：眉眼舒展、嘴角上扬带笑意、神态轻松明亮",
    "angry": "此刻情绪【愤怒】：眉头紧锁、目光凌厉、咬牙或嘴角下压、姿态紧绷有压迫感",
    "sad": "此刻情绪【悲伤】：眼神低垂黯然、眉头微蹙、嘴角下垂、神情哀戚",
    "anxious": "此刻情绪【焦虑不安】：眉头紧蹙、眼神游移闪烁、肩颈微紧、神色惴惴",
    "confident": "此刻情绪【自信笃定】：下巴微抬、目光坚定、嘴角一抹从容、气场沉稳",
}


def _seed_for(key: str) -> int:
    """由稳定 key（如 agent_id）派生固定 seed，让同一角色的基础立绘与各情绪变体锚定同一人物形象。"""
    return zlib.crc32(str(key).encode("utf-8")) % 2_000_000_000

_STYLE = "电影感数字绘景，写实柔和光照，高细节，氛围统一；全系列保持同一画风与色调以便拼接成完整世界。"

# 场景/背景图的负向约束：从机制上（而非仅靠正向措辞）强制「空镜、无人物」，
# 因为文生图模型对正向否定词遵守度不稳，必须经 negative_prompt 通道兜底。
_SCENE_NEGATIVE = (
    "人物, 人, 人脸, 人影, 剪影, 角色, 人群, 背影, 手, 肢体, "
    "person, people, human, man, woman, character, figure, silhouette, crowd, portrait, hands, body, "
    "文字, 水印, 字幕, text, watermark, caption, logo"
)


@dataclass(frozen=True)
class AssetSpec:
    """一张需要的图片：kind=cover|scene|portrait；rel_path 相对 story_dir；size 建议尺寸；prompt 文生图提示词。"""

    kind: str
    key: str          # 标识（cover / place_id / agent_id）
    label: str        # 人读标签
    rel_path: str     # 相对 config/stories/<id>/ 的落点
    size: str         # 建议尺寸，如 "1920×1080"
    prompt: str       # 可直接喂文生图模型的提示词
    negative: str = ""  # 负向提示词（透传给文生图 negative_prompt 通道；场景图据此强制无人物）
    seed: Optional[int] = None  # 固定随机种子（同角色基础图与情绪变体共用，锚定同一形象）
    emotion: str = ""  # 该立绘的情绪标签（仅情绪变体非空；基础立绘为空 = neutral）
    ref_rel_path: str = ""  # 参考图（图生图）：情绪变体以该基础立绘为参考、只改表情，锁住相貌/服饰一致


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
            prompt=f"空镜场景（画面中绝对不出现任何人物）：「{summary}」。"
                   f"只画环境/建筑/家具/自然景观，不出现人、人脸、人影、剪影或任何生物。"
                   f"{mood}留出干净的对话背景空间，{_STYLE}",
            negative=_SCENE_NEGATIVE,
        ))

    # 3a) 玩家立绘（玩家扮演的主角，一张基础立绘；人设取身份/角色——玩家 soul 通常为空）。
    player_meta = meta.get("player") or {}
    p0 = next((a for a in (pack.agents.get("agents") or []) if int(a.get("agent_id", -1)) == 0), None)
    if p0 is not None:
        p_name = p0.get("name") or player_meta.get("name") or "你"
        p_role = p0.get("role") or player_meta.get("role") or ""
        p_persona = _first_sentence(
            p0.get("soul") or player_meta.get("identity") or p_role or "故事的主角", 50)
        role_txt = f"（{p_role}）" if p_role and p_role != "player" else ""
        specs.append(AssetSpec(
            kind="portrait", key="player", label=f"玩家立绘：{p_name}",
            rel_path="assets/avatars/player.png", size="1024×1536",
            prompt=f"人物半身立绘，{p_name}{role_txt}——这是玩家扮演的主角。气质：{p_persona}。"
                   f"正面或四分之三侧面，干净纯色（绿幕）背景便于抠图，{_STYLE}",
            seed=_seed_for("player"),
        ))

    # 3b) 角色立绘（每个非玩家 agent：1 张基础 neutral + 各情绪变体；同 seed 锚定同一形象）
    for a in pack.agents.get("agents", []) or []:
        aid = int(a.get("agent_id", -1))
        if aid == 0:
            continue
        name = a.get("name", f"agent_{aid}")
        persona = _first_sentence(a.get("soul") or "", 70)
        role = a.get("role") or ""
        role_txt = f"（{role}）" if role else ""
        seed = _seed_for(aid)
        base_desc = (f"人物半身立绘，{name}{role_txt}。性格气质：{persona}。"
                     f"正面或四分之三侧面，干净纯色（绿幕）背景便于抠图，{_STYLE}")
        # 基础立绘（neutral）
        specs.append(AssetSpec(
            kind="portrait", key=str(aid), label=f"角色立绘：{name}{role_txt}",
            rel_path=f"assets/avatars/agent_{aid}.png", size="1024×1536",
            prompt=base_desc, seed=seed,
        ))
        # 各情绪变体（以基础立绘为参考做图生图，只改表情，锁住相貌/发型/服饰/构图一致）
        base_rel = f"assets/avatars/agent_{aid}.png"
        for emo in EMOTIONS:
            if emo == "neutral" or emo not in _EMOTION_FACE:
                continue
            specs.append(AssetSpec(
                kind="portrait", key=f"{aid}_{emo}", label=f"角色立绘：{name}（{emo}）",
                rel_path=f"assets/avatars/agent_{aid}_{emo}.png", size="1024×1536",
                prompt=f"保持参考图中人物的相貌、发型、服饰、构图、绿幕背景与画风完全不变，"
                       f"只把面部表情与神态改为——{_EMOTION_FACE[emo]}。",
                seed=seed, emotion=emo, ref_rel_path=base_rel,
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

"""Display metadata helpers for ADV-style frontend presentation."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Tuple

VALID_POSES = frozenset({"neutral", "smirk", "tense", "shocked"})
DEFAULT_POSE = "neutral"
_POSE_RE = re.compile(r"^\[\[display_pose:([a-z_]+)\]\](.*)$", re.DOTALL)


def normalize_pose(value: Any) -> str:
    pose = str(value or "").strip().lower()
    return pose if pose in VALID_POSES else DEFAULT_POSE


def infer_pose_from_text(text: str) -> str:
    content = str(text or "")
    if any(token in content for token in ("？！", "!?", "糟", "不可能", "救命", "完了")):
        return "shocked"
    if any(token in content for token in ("……", "怀疑", "别信", "倒计时", "记仇", "审判")):
        return "tense"
    if any(token in content for token in ("呵", "笑", "行行行", "副作用", "正常人", "可疑")):
        return "smirk"
    return DEFAULT_POSE


def encode_display_content(content: Any, *, fallback_pose: str = DEFAULT_POSE) -> str:
    raw = str(content or "").strip()
    text = raw
    pose = normalize_pose(fallback_pose)

    if raw.startswith("{") and raw.endswith("}"):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            text = str(payload.get("text") or payload.get("content") or "").strip()
            pose = normalize_pose(payload.get("pose"))
            if not text:
                text = raw

    if pose == DEFAULT_POSE:
        pose = infer_pose_from_text(text)
    return f"[[display_pose:{pose}]]{text}"


def parse_display_content(content: Any) -> Tuple[str, Dict[str, str]]:
    raw = str(content or "")
    match = _POSE_RE.match(raw)
    if not match:
        return raw, {"display_pose": infer_pose_from_text(raw)}
    return match.group(2), {"display_pose": normalize_pose(match.group(1))}


def enrich_message_item(item: Dict[str, Any]) -> Dict[str, Any]:
    clean, meta = parse_display_content(item.get("content", ""))
    item["content"] = clean
    item.update(meta)
    return item

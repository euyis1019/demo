#!/usr/bin/env python3
"""P0 烟测：独立验证 f18_scene_render 单帧出图链路（无需 Runner/Flask）。

跑通：SceneState → prompt 组装 →（有 ARK_API_KEY 时）Seedream 出图 → base64 → 还原落盘。
**默认只验证 prompt 组装（不花钱）**；设了 ARK_API_KEY 才真正调一次 Seedream。

    python3 agent_world/hbm_demo/scripts/tests/acceptance/f18_scene_render_smoke.py
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

# 允许直接脚本运行时找到 agent_world 包
_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent_world.hbm_demo.features.f18_scene_render import (  # noqa: E402
    SceneState,
    render_scene_frame,
)
from agent_world.hbm_demo.features.f18_scene_render.prompt_builder import (  # noqa: E402
    build_action_prompt,
    build_anchor_prompt,
)


def main() -> int:
    # 1. prompt 组装（纯本地，不花钱，必须成功）
    scene = SceneState(tick=42, place="negotiation_room", phase="Phase 3",
                       occupant_count=3, has_speaker=True, speaker_id=2)
    anchor = build_anchor_prompt(_as_dict(scene))
    action = build_action_prompt(_as_dict(scene))
    assert "photorealistic" in anchor and "negotiation" in anchor, "锚定 prompt 异常"
    assert "same people" in action, "动作 prompt 异常"
    print(f"[1/2] prompt 组装 OK\n  anchor: {anchor[:90]}...\n  action: {action[:90]}...")

    # 2. 出图：仅当设了 ARK_API_KEY 才真正调用（避免无意花费配额）
    if not os.environ.get("ARK_API_KEY"):
        print("[2/2] SKIP 出图（未设 ARK_API_KEY）；prompt 链路已验证，PASS")
        return 0
    result = render_scene_frame(scene)
    if not result.ok:
        print(f"[2/2] 出图失败: {result.error}")
        return 1
    raw = base64.b64decode(result.image_b64)
    assert raw[:2] in (b"\xff\xd8", b"\x89P"), "非 JPEG/PNG 字节头"
    Path("/tmp/f18_frame_smoke.png").write_bytes(raw)
    print(f"[2/2] 出图 OK {result.elapsed_ms}ms → /tmp/f18_frame_smoke.png ({len(raw)}B)")
    print("PASS")
    return 0


def _as_dict(scene):
    return {"place": scene.place, "phase": scene.phase, "occupant_count": scene.occupant_count,
            "has_speaker": scene.has_speaker, "speaker_id": scene.speaker_id}


if __name__ == "__main__":
    raise SystemExit(main())

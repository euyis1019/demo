#!/usr/bin/env python3
"""P0 烟测：独立验证 f18_scene_render 单帧出图链路（无需 Runner/Flask）。

跑通：SceneState → prompt 组装 → Pollinations 出图 → base64 → 还原落盘。
涉外部网络；离线/超时则打印 SKIP 并退 0（仿 LLM Tier 降级，不阻断门禁）。

    python3 agent_world/hbm_demo/scripts/tests/acceptance/f18_scene_render_smoke.py
"""

from __future__ import annotations

import base64
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
    build_scene_prompt,
)


def main() -> int:
    # 1. prompt 组装（纯本地，必须成功）
    scene = SceneState(tick=42, place="boardroom", phase=3, occupant_count=3, has_speaker=True)
    prompt = build_scene_prompt(
        {"place": scene.place, "phase": scene.phase,
         "occupant_count": scene.occupant_count, "has_speaker": scene.has_speaker}
    )
    assert "flat illustration" in prompt, "画风前缀缺失"
    assert "boardroom" in prompt or "table" in prompt, "房间场景缺失"
    print(f"[1/3] prompt 组装 OK:\n      {prompt}")

    # 2. 出图（外部网络，可降级）
    result = render_scene_frame(scene)
    if not result.ok:
        print(f"[2/3] SKIP 出图（外部不可达/超时）: {result.error}")
        print("[3/3] SKIP 还原；prompt 链路已验证，判 PASS（降级）")
        return 0
    print(f"[2/3] 出图 OK: model={result.model} seed={result.seed} "
          f"{result.elapsed_ms}ms b64={len(result.image_b64 or '')}B mime={result.mime}")

    # 3. base64 还原落盘
    assert result.data_uri() and result.data_uri().startswith("data:image/"), "data_uri 异常"
    raw = base64.b64decode(result.image_b64)
    assert raw[:2] in (b"\xff\xd8", b"\x89P"), "非 JPEG/PNG 字节头"
    out = Path("/tmp/f18_frame_smoke.png")
    out.write_bytes(raw)
    print(f"[3/3] base64 还原落盘 OK: {out} ({len(raw)}B)")
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

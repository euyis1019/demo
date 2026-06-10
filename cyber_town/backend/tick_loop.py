"""世界心跳后台任务：固定墙钟驱动 run_one_tick + 快照广播（方案 §5.2）。

行为契约：
* 单拍耗时超过 ``tick_seconds`` 时立即进下一拍（变速拍）——前端按快照
  携带的 t 渲染，不假设固定节拍；
* ``asyncio.CancelledError`` 显式 break（lifespan shutdown 优雅退出）；
* 任何单拍异常只记日志不退出（与引擎「不可阻断主循环」契约一致）。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

log = logging.getLogger(__name__)


async def tick_loop(
    asm: Any,
    hub: Any,
    snapshot_builder: Any,
    tick_seconds: float,
    affinity_manager: Any = None,
) -> None:
    """持续驱动世界直到任务被 cancel。affinity_manager 参数保留向后兼容（W3 起好感度仅 LLM 主路，tick 内无规则注入）。"""
    log.info("tick_loop 启动：interval=%.2fs affinity=%s",
             tick_seconds, affinity_manager is not None)
    while True:
        t0 = time.monotonic()
        try:
            report = await asm.world_step.run_one_tick()
            snap = await snapshot_builder.build(report)
            await hub.broadcast(snap)
            if report.get("failures"):
                log.warning("t=%s 有 %d 个步骤失败：%s",
                            report.get("t"), len(report["failures"]),
                            report["failures"])
        except asyncio.CancelledError:
            log.info("tick_loop 收到取消信号，优雅退出")
            break
        except Exception as exc:  # noqa: BLE001 — 单拍失败不退场
            log.error("tick 失败：%s", exc, exc_info=True)
        elapsed = time.monotonic() - t0
        try:
            await asyncio.sleep(max(0.0, tick_seconds - elapsed))
        except asyncio.CancelledError:
            log.info("tick_loop 睡眠中被取消，优雅退出")
            break

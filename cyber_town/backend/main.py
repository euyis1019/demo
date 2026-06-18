"""FastAPI 入口：lifespan 装配世界 + 心跳任务 + /ws/world 端点（方案 §5.4）。

运行（从仓库根）：

    # 真实 LLM（backend/.env 需 LLM_API_KEY）
    uvicorn cyber_town.backend.main:app --port 8000

    # Mock 模式（离线剧本，开发/CI 用）
    CYBER_TOWN_MOCK=1 uvicorn cyber_town.backend.main:app --port 8000

环境变量开关（均可缺省）：
* ``CYBER_TOWN_MOCK=1``         用 MockLLMClient（不调真实 LLM）
* ``CYBER_TOWN_SCENARIO=path``  自定义世界种子
* ``CYBER_TOWN_SIM_DIR=path``   world.db 落盘目录（默认 tempdir）
* ``CYBER_TOWN_TICK_SECONDS``   心跳间隔（默认 config.TICK_SECONDS）
* ``CYBER_TOWN_DIRECTORS=0``    关闭管理类 agent（回退全员每拍激活、无环境事件）
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from cyber_town.backend.affinity import AffinityManager, AffinityStore
from cyber_town.backend.affinity.manager import DEFAULT_SEED
from cyber_town.backend.config import (
    DEFAULT_SCENARIO_PATH,
    PLAYER_ID,
    TICK_SECONDS,
    LLMConfig,
    resolve_llm_config,
)
from cyber_town.backend.directors import ActivationDirector, WorldDirector
from cyber_town.backend.llm.client import make_llm_client
from cyber_town.backend.api.snapshot import SnapshotBuilder
from cyber_town.backend.runtime.tick_loop import tick_loop
from cyber_town.backend.api.timeline import build_timeline
from cyber_town.backend.runtime.world_factory import build_world
from cyber_town.backend.api.ws_hub import WSHub
from cyber_town.world_seed.loader import load_scenario

# uvicorn 只配置自家 logger，根 logger 无 handler 会吞掉应用 INFO 日志；
# basicConfig 在根 logger 已有 handler 时是 no-op，安全
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)

# Mock 模式占位配置（不需要真实 key——离线剧本不发网络请求）
_MOCK_LLM_CFG = LLMConfig(base_url="http://mock", model="mock", api_key="mock")


def create_app(
    scenario_path: Optional[str] = None,
    *,
    mock: Optional[bool] = None,
    tick_seconds: Optional[float] = None,
    sim_dir: Optional[str] = None,
) -> FastAPI:
    """应用工厂：参数优先，环境变量兜底（便于测试注入）。"""
    cfg_scenario = scenario_path or os.environ.get(
        "CYBER_TOWN_SCENARIO", str(DEFAULT_SCENARIO_PATH)
    )
    cfg_mock = mock if mock is not None else (
        os.environ.get("CYBER_TOWN_MOCK", "") in ("1", "true", "yes")
    )
    cfg_tick = tick_seconds if tick_seconds is not None else float(
        os.environ.get("CYBER_TOWN_TICK_SECONDS", TICK_SECONDS)
    )
    cfg_sim_dir = sim_dir or os.environ.get("CYBER_TOWN_SIM_DIR")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # ---- startup：装配必须在心跳任务启动前同步完成 ------------------
        scenario = load_scenario(cfg_scenario)
        if cfg_mock:
            llm_cfg = _MOCK_LLM_CFG
        else:
            llm_cfg = resolve_llm_config(scenario.get("llm", {}) or {})
        client = make_llm_client(llm_cfg, mock=cfg_mock)
        run_dir = Path(cfg_sim_dir) if cfg_sim_dir else Path(
            tempfile.mkdtemp(prefix="cyber_town_ws_")
        )
        asm = await build_world(scenario, run_dir, client, llm_cfg)
        # ---- M4 好感度薄层：装配后接线（与 world_factory 解耦）------------
        affinity_store = AffinityStore(run_dir / "affinity.db", player_id=PLAYER_ID)
        affinity_store.seed(DEFAULT_SEED)
        affinity_mgr = AffinityManager(
            affinity_store, asm.name_directory, player_id=PLAYER_ID,
        )
        affinity_mgr.wire_npcs(asm.npcs)

        # ---- W5 管理类 agent（只调配资源与感知输入，不产生 NPC 行为）----
        directors = []
        world_dir = None
        if os.environ.get("CYBER_TOWN_DIRECTORS", "1") not in ("0", "false"):
            act_dir = ActivationDirector(
                client, llm_cfg.model, [n.agent_id for n in asm.npcs])
            asm.scheduler.interval_provider = act_dir.interval_of
            world_dir = WorldDirector(client, llm_cfg.model)
            for npc in asm.npcs:
                npc.world_event_provider = world_dir.render_for_npc
            directors = [act_dir, world_dir]
            log.info("管理类 agent 已启用：激活导演 + 世界事件导演")

        hub = WSHub()
        snapshot_builder = SnapshotBuilder(
            asm, tick_seconds=cfg_tick, affinity_manager=affinity_mgr,
            world_director=world_dir,
        )

        app.state.asm = asm
        app.state.hub = hub
        app.state.snapshot_builder = snapshot_builder
        app.state.tick_task = asyncio.create_task(
            tick_loop(asm, hub, snapshot_builder, cfg_tick,
                      affinity_manager=affinity_mgr, directors=directors)
        )
        log.info(
            "世界已启动：mock=%s tick=%.2fs sim_dir=%s", cfg_mock, cfg_tick, run_dir,
        )
        try:
            yield
        finally:
            # ---- shutdown：cancel → await → close（防 world.db 残写）----
            app.state.tick_task.cancel()
            try:
                await app.state.tick_task
            except asyncio.CancelledError:
                pass
            try:
                asm.world_db.close()
            except Exception:  # noqa: BLE001 — 关库失败只记日志
                log.warning("world_db.close() 失败", exc_info=True)
            affinity_store.close()
            log.info("世界已关停")

    app = FastAPI(title="赛博小镇后端", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict:
        asm = getattr(app.state, "asm", None)
        if asm is None:  # lifespan 未完成（启动窗口期）
            raise HTTPException(status_code=503, detail="世界尚未就绪")
        return {
            "status": "ok",
            "t": int(asm.world.clock.t),
            "clients": app.state.hub.client_count,
            "agents": len(asm.all_agents),
        }

    @app.get("/agents/{agent_id}/timeline")
    async def agent_timeline(agent_id: int, limit: int = 60) -> dict:
        """M6 档案页：某 agent 的行为时间线（对话/OS/移动/目标）。"""
        asm = getattr(app.state, "asm", None)
        if asm is None:
            raise HTTPException(status_code=503, detail="世界尚未就绪")
        if agent_id not in {a.agent_id for a in asm.all_agents}:
            raise HTTPException(status_code=404, detail=f"agent {agent_id} 不存在")
        return {
            "agent_id": agent_id,
            "name": asm.name_directory.get(agent_id, f"agent_{agent_id}"),
            "entries": build_timeline(asm, agent_id, limit=limit),
        }

    @app.websocket("/ws/world")
    async def ws_world(ws: WebSocket) -> None:
        hub: WSHub = app.state.hub
        await hub.register(ws, app.state.snapshot_builder.hello())
        await hub.handle_client(ws, app.state.asm.player)

    # ---- Web 版游戏静态托管（浏览器即玩）-------------------------------
    # 前端：真 3D 版 frontend_web（Three.js/R3F）。
    # 出包：cd cyber_town/frontend_web && npm run build（产物 dist，base 已设 /game/）
    dist = Path(__file__).parent.parent / "frontend_web" / "dist"
    if (dist / "index.html").exists():
        app.mount("/game", StaticFiles(directory=str(dist), html=True), name="game")
        log.info("Web 前端托管：frontend_web（/game）")

        @app.get("/")
        async def index() -> RedirectResponse:
            return RedirectResponse(url="/game/")
    else:
        log.warning("未发现前端产物（%s）——先 cd cyber_town/frontend_web && npm run build", dist)

    return app


# uvicorn cyber_town.backend.main:app 的默认入口（读环境变量）
app = create_app()

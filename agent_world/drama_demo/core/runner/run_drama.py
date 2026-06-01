"""drama demo Runner — seed world + LLM agents + resident world loop + IPC.

Usage:
    python -m agent_world.drama_demo.run_drama \\
        --config agent_world/drama_demo/drama_scenario.yaml \\
        --sim-dir agent_world/drama_demo/sim/canglan_sword/
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

from agent_world.drama_demo.core.runner.ipc_handlers import wire_handlers
from agent_world.drama_demo.core.runner.kernel import build_kernel
from agent_world.drama_demo.core.runner.world_loop import WorldLoopOrchestrator
from agent_world.drama_demo.shared.config_loader import load_scenario
from agent_world.drama_demo.shared.env_status import patch_ipc_server_env_status, write_env_status
from agent_world.ipc.server import IPCServer

log = logging.getLogger("agent_world.drama_demo")

_DRAMA_DEMO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = _DRAMA_DEMO_ROOT / "drama_scenario.yaml"
DEFAULT_SIM_DIR = _DRAMA_DEMO_ROOT / "sim" / "canglan_sword"


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="drama demo simulation runner")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to drama_scenario.yaml",
    )
    parser.add_argument(
        "--sim-dir",
        type=Path,
        default=DEFAULT_SIM_DIR,
        help="Simulation directory (world.db + ipc + env_status.json)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args(argv)


async def _run(sim_dir: Path, scenario: dict) -> int:
    kernel = await build_kernel(scenario, sim_dir)
    sim_dir_str = str(sim_dir.resolve())

    write_env_status(sim_dir_str, kernel.clock.t, status="starting")

    orchestrator = WorldLoopOrchestrator(
        world_db=kernel.world_db,
        world_state=kernel.world_state,
        place_store=kernel.place_store,
        script_engine=kernel.script_engine,
        world_step=kernel.world_step,
        agents=kernel.agents,
        sim_dir=sim_dir_str,
        get_current_tick=lambda: int(kernel.world_state.clock.t),
    )

    ipc_server = IPCServer(
        simulation_dir=sim_dir_str,
        world_state=kernel.world_state,
        script_engine=kernel.script_engine,
    )

    def _loop_extra() -> dict:
        if orchestrator.enabled:
            return orchestrator.get_loop_status()
        return {}

    patch_ipc_server_env_status(
        ipc_server,
        sim_dir_str,
        lambda: int(kernel.world_state.clock.t),
        get_loop_extra=_loop_extra,
    )
    wire_handlers(
        ipc_server,
        world_db=kernel.world_db,
        world_state=kernel.world_state,
        place_store=kernel.place_store,
        relation_graph=kernel.relation_graph,
        capability_table=kernel.capability_table,
        connectivity=kernel.connectivity,
        script_engine=kernel.script_engine,
        world_step=kernel.world_step,
        agents=kernel.agents,
        scenario=scenario,
        segment_store=kernel.world_step.segments,
        sim_dir=sim_dir_str,
        get_current_tick=lambda: int(kernel.world_state.clock.t),
        orchestrator=orchestrator,
    )

    write_env_status(
        sim_dir_str,
        kernel.clock.t,
        status="running",
        loop_running=orchestrator.enabled,
        loop_state="running" if orchestrator.enabled else "disabled",
        last_activity_t=int(kernel.clock.t),
        queue_depth=0,
    )
    log.info(
        "HBM runner ready sim_dir=%s simulation_id=%s agents=%d places=%d world_loop=%s",
        sim_dir_str,
        scenario.get("simulation_id"),
        len(kernel.agents),
        len(scenario.get("places", [])),
        orchestrator.enabled,
    )

    def _request_stop(*_args: object) -> None:
        log.info("shutdown requested")
        ipc_server.stop()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _request_stop())

    await orchestrator.start()
    try:
        await ipc_server.run_forever()
    finally:
        await orchestrator.stop()
        write_env_status(sim_dir_str, kernel.clock.t, status="stopped", loop_running=False)
        kernel.world_db.close()
        log.info("HBM runner exit")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config_path = args.config.resolve()
    sim_dir = args.sim_dir.resolve()

    # 数据驱动：默认从活跃 Story Pack 播种世界（env DRAMA_STORY_ID，默认 canglan_sword）。
    # L1 只读 shared/ 的助手（不违反 D4）。校验不过即抛，拒绝带病启动。
    from agent_world.drama_demo.shared.story_pack import (
        list_story_ids,
        load_and_validate_story_pack,
    )
    from agent_world.drama_demo.shared.story_pack.scenario_adapter import (
        is_story_pack_seed_enabled,
        story_pack_to_scenario,
    )

    if is_story_pack_seed_enabled():
        from agent_world.drama_demo.shared.story_config import active_story_id

        sid = active_story_id()  # 决定播哪个故事
        if sid not in list_story_ids():
            log.error("活跃故事 '%s' 无对应 Story Pack（config/stories/%s/）", sid, sid)
            return 1
        pack = load_and_validate_story_pack(sid)  # 校验不过即抛
        scenario = story_pack_to_scenario(pack)
        log.info("从 Story Pack '%s' 播种世界", sid)
    else:
        # 仅当显式关闭播种时才需要外部 scenario 文件。
        if not config_path.is_file():
            log.error("config not found: %s", config_path)
            return 1
        scenario = load_scenario(config_path)

    try:
        return asyncio.run(_run(sim_dir, scenario))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())

"""内核装配：scenario → 可运行的 agent_world 世界（AssembledWorld）。

唯一成套 import agent_world 的模块（其余模块保持与引擎解耦）。
装配姿势 1:1 照搬引擎自带范例 agent_world/demo/run_demo.py::_build_kernel，
差异点：

* agents 分两类构建——``CyberTownNPC``（LLM 村民）+ ``PlayerAgent``
  （玩家虚拟农夫，scenario 里 ``is_player: true`` 标记）；
* ``scheduler`` 传 ``ActivationScheduler``（同场每拍 + 异地心跳），
  **永不传 None**（审计 SEED-5：agent_id=0 在默认路径有真值陷阱）；
* 装配末尾断言 dispatcher / perception_builder 非 None（审计 C1：
  step 7.b 的 dispatcher.dispatch 无 None-check）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_world.buses.face_to_face import FaceToFaceBus
from agent_world.buses.group_message import GroupMessageBus
from agent_world.buses.remote_message import RemoteMessageBus
from agent_world.memory.segment import SegmentStore
from agent_world.persistence.world_db import WorldDB
from agent_world.world.capability_table import CapabilityTable
from agent_world.world.clock import Clock
from agent_world.world.connectivity import ConnectivityResolver
from agent_world.world.dispatcher import ActionDispatcher
from agent_world.world.perception import PerceptionBuilder
from agent_world.world.place_store import PlaceStore
from agent_world.world.relation_graph import RelationGraph
from agent_world.world.state import WorldState
from agent_world.world.step import WorldStep

from cyber_town.backend.config import (
    PLAYER_ID,
    SEGMENT_HEADERS,
    LLMConfig,
)
from cyber_town.backend.npc import CyberTownNPC
from cyber_town.backend.player_agent import PlayerAgent
from cyber_town.backend.scheduler import ActivationScheduler
from cyber_town.world_seed.loader import seed_into_db

log = logging.getLogger(__name__)


class _NullPoolManager:
    """pools 子系统占位（vendor/oasis 缺失，本 demo 无 FEED 动作）。

    传实例而非 None——引擎 dispatcher 的 pools 路径没有 None-check
    （审计 NULL-POOL-1，姿势同 run_demo）。
    """

    pools: Dict[str, Any] = {}

    def feeds_at(self, place_id: str) -> List[str]:  # noqa: ARG002
        return []

    def platform_for(self, place_id: str, feed: str) -> None:  # noqa: ARG002
        return None

    async def update_all(self) -> None:
        return None

    async def dispatch(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ARG002
        raise RuntimeError("FEED 动作在赛博小镇中未启用")


@dataclass
class AssembledWorld:
    """装配产物：后续各层（CLI / FastAPI / snapshot）的统一入口。"""

    world: WorldState
    world_step: WorldStep
    world_db: WorldDB
    player: PlayerAgent
    npcs: List[CyberTownNPC]
    name_directory: Dict[int, str]
    scenario: Dict[str, Any]
    perception: PerceptionBuilder
    dispatcher: ActionDispatcher
    scheduler: ActivationScheduler
    # 运行时恒非 None（build_world 必建）；Optional 仅为与下游引擎
    # 「可选依赖容忍 None」的接口契约保持类型一致（审查 TYPE-MISMATCH-1）
    segment_store: Optional[SegmentStore] = field(repr=False, default=None)

    @property
    def all_agents(self) -> List[Any]:
        """玩家 + NPC（按 agent_id 升序），供报表/快照遍历。"""
        return sorted([self.player, *self.npcs], key=lambda a: a.agent_id)


async def build_world(
    scenario: Dict[str, Any],
    sim_dir: Path,
    llm_client: Any,
    llm_cfg: LLMConfig,
) -> AssembledWorld:
    """从 scenario 构建完整内核 + agents，返回 AssembledWorld。"""
    sim_dir.mkdir(parents=True, exist_ok=True)
    world_db = WorldDB(str(sim_dir / "world.db"))
    world_db.init_schema()  # 必须在任何后台任务启动前同步完成

    clock = Clock(t0=0)
    place_store = PlaceStore(world_db)
    relation_graph = RelationGraph(world_db)
    capability_table = CapabilityTable(world_db)
    connectivity = ConnectivityResolver(
        places=place_store, relations=relation_graph, caps=capability_table,
    )

    await seed_into_db(world_db, capability_table, relation_graph, connectivity, scenario)

    place_store.load_from_db(world_db)
    relation_graph.load_from_db(world_db)
    capability_table.load_from_db(world_db)

    pool_manager = _NullPoolManager()
    f2f_bus = FaceToFaceBus(
        world_db=world_db, places=place_store,
        connectivity=connectivity, clock=clock,
    )
    rdc_bus = RemoteMessageBus(
        world_db=world_db, places=place_store, relations=relation_graph,
        caps=capability_table, connectivity=connectivity, clock=clock,
    )
    grp_bus = GroupMessageBus(
        world_db=world_db, places=place_store,
        connectivity=connectivity, clock=clock,
    )

    # max_raw_actions 调大供档案页时间线回看（compressor=None 不清理，内存可控）
    segment_store = SegmentStore(max_raw_actions=120)
    perception = PerceptionBuilder(
        world_db=world_db, places=place_store, relations=relation_graph,
        caps=capability_table, connectivity=connectivity,
        retriever=None, script_engine=None, pool_manager=None,
        segment_headers=SEGMENT_HEADERS,
    )
    world_state = WorldState(
        world_db=world_db, places=place_store, relations=relation_graph,
        caps=capability_table, clock=clock, pool_manager=pool_manager,
    )
    dispatcher = ActionDispatcher(
        world_state=world_state,
        f2f_bus=f2f_bus, rdc_bus=rdc_bus, grp_bus=grp_bus,
        pool_manager=pool_manager,
        script_engine=None, compressor=None,
        segment_store=segment_store,
    )

    # ---- agents ------------------------------------------------------------
    name_directory: Dict[int, str] = {
        int(a["agent_id"]): a.get("name", f"agent_{a['agent_id']}")
        for a in scenario.get("agents", [])
    }
    available_places = [p["place_id"] for p in scenario.get("places", [])]
    groups_for_agent = _index_groups_by_member(scenario)

    clock_cfg = scenario.get("clock") or {}
    wall_start = str(clock_cfg.get("start_time", "08:00")).strip()
    minutes_per_tick = int(clock_cfg.get("minutes_per_tick", 5))

    player: PlayerAgent | None = None
    npcs: List[CyberTownNPC] = []
    for a in scenario.get("agents", []):
        aid = int(a["agent_id"])
        if a.get("is_player") or aid == PLAYER_ID:
            player = PlayerAgent(
                agent_id=aid,
                name=a.get("name", "农场主"),
                soul=(a.get("soul") or "").strip(),
                long_term_goal=(a.get("long_term_goal") or "").strip(),
                current_state=(a.get("current_state") or "").strip(),
                groups=groups_for_agent.get(aid, []),
            )
            world_state.register_agent(aid, player)
            continue
        npc = CyberTownNPC(
            agent_id=aid,
            name=a.get("name", f"agent_{aid}"),
            soul=(a.get("soul") or "").strip(),
            long_term_goal=(a.get("long_term_goal") or "").strip(),
            current_state=(a.get("current_state") or "").strip(),
            short_term_goal=(a.get("short_term_goal") or "").strip(),
            groups=groups_for_agent.get(aid, []),
            name_directory=name_directory,
            available_places=available_places,
            perception_builder=perception,
            segment_store=segment_store,
            client=llm_client,
            model=llm_cfg.model,
            temperature=llm_cfg.temperature,
            max_tokens=llm_cfg.max_tokens,
            llm_timeout=llm_cfg.timeout,
            wall_start_time=wall_start,
            minutes_per_tick=minutes_per_tick,
        )
        world_state.register_agent(aid, npc)
        npcs.append(npc)

    if player is None:
        raise ValueError("scenario 里必须有一个 is_player: true（或 agent_id=0）的玩家 agent")

    scheduler = ActivationScheduler(player_id=player.agent_id)

    # C1 对策：有 agents 时 dispatcher/perception 绝不能为 None（引擎无兜底）
    assert dispatcher is not None and perception is not None

    world_step = WorldStep(
        world_state=world_state,
        perception_builder=perception,
        dispatcher=dispatcher,
        script_engine=None,
        pool_manager=pool_manager,
        f2f_bus=f2f_bus, rdc_bus=rdc_bus, grp_bus=grp_bus,
        segment_store=segment_store,
        compressor=None,
        world_db=world_db,
        scheduler=scheduler,
        sim_id=scenario.get("simulation_id", "cyber_town"),
    )

    log.info(
        "世界装配完成：player=%s(%d) npcs=%s（全员每拍激活）",
        player.name, player.agent_id,
        [f"{n.name}({n.agent_id})" for n in npcs],
    )
    return AssembledWorld(
        world=world_state, world_step=world_step, world_db=world_db,
        player=player, npcs=npcs, name_directory=name_directory,
        scenario=scenario, perception=perception, dispatcher=dispatcher,
        scheduler=scheduler, segment_store=segment_store,
    )


def _index_groups_by_member(scenario: Dict[str, Any]) -> Dict[int, List[Dict[str, Any]]]:
    """群成员索引：agent_id -> [{group_id, name, members}, ...]。"""
    out: Dict[int, List[Dict[str, Any]]] = {}
    for g in scenario.get("groups", []) or []:
        gid = int(g["group_id"])
        members = [int(m) for m in g.get("members", [])]
        for aid in members:
            out.setdefault(aid, []).append(
                {"group_id": gid, "name": g.get("name"), "members": members}
            )
    return out

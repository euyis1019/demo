"""世界种子灌库：scenario.yaml → WorldDB / CapabilityTable / RelationGraph。

逻辑 1:1 照搬 agent_world/demo/run_demo.py::_seed_world（引擎自带范例的
标准姿势），关键点：

* coverage 的 self-edge ``(p, p)`` **必须在这里显式补全**（latency=0,
  can_reach=1）——这不是引擎自动行为；同地点 F2F 与同场 RDC 即达都依赖它
  （方案 §8 不变量 3 / M0 验收项 V4）。
* group_id 在 YAML 显式给出时走 raw ``INSERT OR REPLACE`` 保留 id
  （``WorldDB.insert_group`` 会忽略 id 走 AUTOINCREMENT）。
* relation 的 ``symmetric: true`` 在这里补反向边——``neighbor`` 是未注册
  关系类型，引擎默认 meta 为 ``symmetric=False``。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

import yaml

log = logging.getLogger(__name__)


def load_scenario(path: str | Path) -> Dict[str, Any]:
    """读取并解析 scenario.yaml，返回原始 dict（不做业务加工）。"""
    with Path(path).open("r", encoding="utf-8") as fh:
        scenario = yaml.safe_load(fh) or {}
    if not scenario.get("places") or not scenario.get("agents"):
        raise ValueError(f"种子文件缺少 places/agents：{path}")
    return scenario


async def seed_into_db(
    world_db: Any,
    capability_table: Any,
    relation_graph: Any,
    connectivity: Any,
    scenario: Dict[str, Any],
) -> None:
    """把 places / coverage / 初始位置 / capabilities / groups / relations 灌进世界。

    调用时机：``WorldDB.init_schema()`` 之后、各 store ``load_from_db`` 之前。
    """
    # ---- places -----------------------------------------------------------
    for p in scenario.get("places", []):
        attrs = p.get("attrs") or {}
        await world_db.upsert_place(
            place_id=p["place_id"],
            place_type=p.get("place_type", "default"),
            parent_id=p.get("parent_id"),
            capacity=p.get("capacity"),
            attrs=json.dumps(attrs, ensure_ascii=False),
        )

    # ---- coverage（显式边 + self-edge 补全）--------------------------------
    for c in scenario.get("coverage", []) or []:
        await world_db.upsert_coverage(
            src_place=c["src"],
            dst_place=c["dst"],
            latency_ticks=int(c.get("latency_ticks", 0)),
            can_reach=int(c.get("can_reach", 1)),
        )
    # self-edge：F2F 同地点零延迟 / 同场 RDC 即达 都依赖它（V4）
    for p in scenario.get("places", []):
        await world_db.upsert_coverage(
            src_place=p["place_id"],
            dst_place=p["place_id"],
            latency_ticks=0,
            can_reach=1,
        )

    # ---- 初始位置 ----------------------------------------------------------
    for a in scenario.get("agents", []):
        await world_db.set_location(
            agent_id=int(a["agent_id"]),
            place_id=a["location"],
            t=0,
        )

    # ---- capabilities ------------------------------------------------------
    for entry in scenario.get("capabilities", []) or []:
        await capability_table.grant(
            int(entry["agent_id"]), str(entry["capability"]),
        )

    # ---- groups（保留显式 group_id）---------------------------------------
    group_members_map: Dict[int, set] = {}
    for g in scenario.get("groups", []) or []:
        group_id = int(g["group_id"])
        async with world_db._write_lock:  # noqa: SLF001 — 与 run_demo 同款姿势
            world_db._exec(  # noqa: SLF001
                "INSERT OR REPLACE INTO chat_group(group_id, name) VALUES(?, ?)",
                (group_id, str(g.get("name") or f"group_{group_id}")),
            )
        members = [int(m) for m in g.get("members", [])]
        for aid in members:
            await world_db.insert_group_member(group_id, aid)
            await world_db.insert_group_event(
                group_id=group_id,
                agent_id=aid,
                event_type="join",
                occurred_at=-1,
                actor_id=int(g.get("creator_id", aid)),
            )
        group_members_map[group_id] = set(members)

    # phi_grp 依赖 ConnectivityResolver 内存里的成员表
    if hasattr(connectivity, "set_group_members"):
        for gid, members in group_members_map.items():
            connectivity.set_group_members(gid, members)

    # ---- relations（symmetric 补反向边）------------------------------------
    for r in scenario.get("relations", []) or []:
        src, dst = int(r["src"]), int(r["dst"])
        rtype = str(r.get("type", "contact"))
        await relation_graph.add(src, dst, rtype, t=0)
        if r.get("symmetric") and src != dst:
            try:
                await relation_graph.add(dst, src, rtype, t=0)
            except Exception as exc:  # noqa: BLE001 — 多为对称 meta 已自动补边
                log.debug("反向关系 %s->%s(%s) 跳过：%s", dst, src, rtype, exc)

    log.info(
        "世界种子灌库完成：%d 地点 / %d agent / %d 群",
        len(scenario.get("places", [])),
        len(scenario.get("agents", [])),
        len(scenario.get("groups", []) or []),
    )

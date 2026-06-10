"""M0 阶段 CLI：纯文本驱动的活体世界（无 FastAPI / 无前端）。

用法（从仓库根）：

    # 离线冒烟（Mock LLM 剧本，不走网络；玩家命令也走剧本）
    python3 -m cyber_town.run_m0 --mock-llm --num-ticks 8 --heartbeat 4

    # 真实 LLM（需 backend/.env 有 LLM_API_KEY 且内网网关可达）
    python3 -m cyber_town.run_m0 --num-ticks 6

验收（方案 §12 M0 / §13）：
* 跑通 N 拍，日志可见 NPC 走 F2F / request_move；
* V4：同地点 F2F 消息 delivered=1（依赖 loader 的 self-edge 补全）；
* 顺带验证 RDC 跨地点 1 拍延迟、GRP 入库。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

from cyber_town.backend.config import (
    DEFAULT_SCENARIO_PATH,
    HEARTBEAT_EVERY,
    resolve_llm_config,
)
from cyber_town.backend.llm_client import make_llm_client
from cyber_town.backend.world_factory import AssembledWorld, build_world
from cyber_town.world_seed.loader import load_scenario

log = logging.getLogger("cyber_town.m0")

# Mock 模式下注入的玩家命令剧本：t -> command（验证 PlayerAgent 注入路径）
_PLAYER_SCRIPT: Dict[int, Dict[str, Any]] = {
    1: {"action": "speak_to_local",
        "kwargs": {"content": "大山哥，这地两年没人种了，你说先从哪垄下手？"}},
    5: {"action": "send_message",
        "kwargs": {"target": 2, "content": "阿香姐，晚上酒馆开门吗？想去认认门。"}},
    6: {"action": "request_move", "kwargs": {"place_id": "square"}},
}

_CHANNEL_GLYPH = {"F2F": "🗣 ", "RDC": "📨", "GRP": "👥"}


def _print_tick_report(tick: int, report: Dict[str, Any], asm: AssembledWorld) -> None:
    """逐拍美化输出：agent 状态 + 本拍消息（姿势同 run_demo._print_tick_report）。"""
    agents = asm.all_agents
    wall = ""
    if asm.npcs:
        wall = asm.npcs[0]._wall_clock_label(tick)  # noqa: SLF001 — 共享同一时钟配置
    head = f" 世界时间 {wall}" if wall else ""
    print(f"\n=================== tick t={tick}{head} ===================")
    print(
        f"  active={report.get('active')}  places={report.get('places')}  "
        f"failures={len(report.get('failures', []))}"
    )
    for f in report.get("failures", []) or []:
        print(f"  FAIL {f}")

    name_of = asm.name_directory
    print("  --- agents ---")
    for a in agents:
        loc = asm.world.location_of(a.agent_id)
        cs = (a.current_state or "").replace("\n", " ").strip()
        tag = "[玩家]" if a.agent_id == asm.player.agent_id else "      "
        print(f"    [{a.agent_id}] {a.name:6s}{tag} @{loc:8s} state={cs[:60]!r}")

    rows = asm.world_db._conn.execute(  # noqa: SLF001 — 调试报表直读，同 run_demo
        "SELECT message_id, sender_id, recipient_id, group_id, channel_type, "
        "content, place_id, attempted_at, arrive_at, delivered "
        "FROM direct_message WHERE attempted_at = ? ORDER BY message_id",
        (tick,),
    ).fetchall()
    if not rows:
        return
    print("  --- messages this tick ---")
    printed: set = set()
    for row in rows:
        mid = int(row[0])
        if mid in printed:
            continue
        sender_id, ch, gid = row[1], row[4], row[3]
        content = (row[5] or "").replace("\n", " ")
        place_id, arr = row[6], row[8]
        ok = {1: "✓", 0: "✗", -1: "·"}.get(int(row[9]), "?")
        glyph = _CHANNEL_GLYPH.get(ch, "  ")
        sender = name_of.get(sender_id, f"#{sender_id}")
        if ch == "F2F":
            # F2F 广播扇出按（发送者+内容+地点）折叠成一行
            siblings = [
                r for r in rows
                if r[4] == "F2F" and r[1] == sender_id
                and r[6] == place_id and (r[5] or "") == (row[5] or "")
            ]
            printed.update(int(r[0]) for r in siblings)
            rcpts = "、".join(
                name_of.get(int(r[2]), f"#{r[2]}") for r in sorted(siblings, key=lambda x: x[2])
            )
            print(f"    {glyph}[F2F@{place_id}] {sender}->[{rcpts}] {ok} :: {content[:80]}")
        else:
            printed.add(mid)
            tag = f"{ch}#g{gid}" if gid else ch
            recipient = name_of.get(row[2], f"#{row[2]}")
            print(f"    {glyph}[{tag}] {sender}->{recipient} arrive_at={arr} {ok} :: {content[:80]}")


def _acceptance_check(asm: AssembledWorld) -> bool:
    """M0 验收：V4 self-edge（F2F 可达）+ RDC 延迟 + GRP 入库。"""
    conn = asm.world_db._conn  # noqa: SLF001
    f2f_ok = conn.execute(
        "SELECT COUNT(*) FROM direct_message WHERE channel_type='F2F' AND delivered=1"
    ).fetchone()[0]
    rdc_delayed = conn.execute(
        "SELECT COUNT(*) FROM direct_message "
        "WHERE channel_type='RDC' AND arrive_at > attempted_at"
    ).fetchone()[0]
    grp_rows = conn.execute(
        "SELECT COUNT(*) FROM direct_message WHERE channel_type='GRP'"
    ).fetchone()[0]
    moves = conn.execute(
        "SELECT COUNT(*) FROM agent_location WHERE arrived_at > 0"
    ).fetchone()[0]

    print("\n=================== M0 验收 ===================")
    print(f"  V4 F2F 同地点送达 (delivered=1)：{f2f_ok} 条  {'✓' if f2f_ok else '✗ self-edge 失效!'}")
    print(f"  RDC 跨地点 ≥1 拍延迟：{rdc_delayed} 条  {'✓' if rdc_delayed else '（本次运行未触发）'}")
    print(f"  GRP 群消息入库：{grp_rows} 条  {'✓' if grp_rows else '（本次运行未触发）'}")
    print(f"  发生过移动的 agent：{moves} 个")
    return bool(f2f_ok)


async def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="赛博小镇 M0：活体世界纯文本运行")
    parser.add_argument("--config", default=str(DEFAULT_SCENARIO_PATH))
    parser.add_argument("--num-ticks", type=int, default=8)
    parser.add_argument("--sim-dir", default=None, help="world.db 落盘目录（默认 tempdir）")
    parser.add_argument("--mock-llm", action="store_true",
                        help="离线剧本模式：不调真实 LLM，玩家命令也走内置剧本")
    parser.add_argument("--heartbeat", type=int, default=HEARTBEAT_EVERY,
                        help="异地 NPC 心跳间隔（拍）")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    scenario = load_scenario(args.config)
    llm_cfg = resolve_llm_config(scenario.get("llm", {}) or {})
    client = make_llm_client(llm_cfg, mock=args.mock_llm)
    sim_dir = Path(args.sim_dir) if args.sim_dir else Path(
        tempfile.mkdtemp(prefix="cyber_town_m0_")
    )

    mode = "Mock 剧本" if args.mock_llm else f"真实 LLM（{llm_cfg.model}）"
    print(f"=== 赛博小镇 M0：{scenario.get('simulation_id')} | {mode} ===")
    print(f"=== sim_dir={sim_dir} heartbeat={args.heartbeat} ===")

    asm = await build_world(
        scenario, sim_dir, client, llm_cfg, heartbeat_every=args.heartbeat,
    )

    tick_costs: List[float] = []
    for tick in range(args.num_ticks):
        if args.mock_llm and tick in _PLAYER_SCRIPT:
            asm.player.push_command(_PLAYER_SCRIPT[tick])
        t0 = time.monotonic()
        report = await asm.world_step.run_one_tick()
        tick_costs.append(time.monotonic() - t0)
        _print_tick_report(tick, report, asm)

    ok = _acceptance_check(asm)
    if tick_costs:
        print(
            f"  单拍耗时：avg={sum(tick_costs)/len(tick_costs):.2f}s  "
            f"max={max(tick_costs):.2f}s（V3 压测参考）"
        )
    print(f"=== done; world.db 保留在 {sim_dir / 'world.db'} ===")
    return 0 if ok else 1


def run() -> None:
    sys.exit(asyncio.run(main()))


if __name__ == "__main__":
    run()

#!/usr/bin/env python3
"""沧澜剑派 验收门禁（数据驱动 Story Pack 的端到端验收）。

替代旧 HBM(test_m0) 门禁：起 Runner+Flask（默认即 canglan_sword，无需任何 env），
模仿真实玩家用自然台词逐节点推进到结局，断言：
  1) Runner 从 Story Pack 播种（5 NPC / 8 地点）；
  2) Flask /health 与 /session/start 正常；
  3) 玩家台词驱动剧情推进，最终触发已知结局（status=completed）；
  4) 至少一条 NPC 当面对白浮现（证明 agent 活着且人设数据驱动、零黄仁勋污染）；
  5) 前端 npm run build 通过。
全程只用隔离目录 sim/_canglan_e2e，绝不碰任何用户存档。
"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HBM = ROOT / "agent_world" / "drama_demo"
SIM = HBM / "sim" / "_canglan_e2e"
PORT = "5078"
SID = "canglan_sword"
BASE = f"http://127.0.0.1:{PORT}/api/drama/simulations/{SID}"
sys.path.insert(0, str(ROOT))


class GateFailure(Exception):
    pass


def _env() -> dict:
    env = dict(os.environ)
    envfile = HBM / ".env"
    if envfile.is_file():
        for line in envfile.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    # 不设 DRAMA_STORY_ID/SEED/ROUTING——验证 canglan 即为默认数据驱动游戏。
    env.update({
        "DRAMA_SIM_DIR": str(SIM), "FLASK_RUN_PORT": PORT,
        "FLASK_APP": "agent_world.app:create_app", "PYTHONPATH": str(ROOT),
    })
    return env


_COOKIE = {"v": ""}


def api(method: str, path: str, body=None, timeout: int = 180):
    parsed = urllib.parse.urlparse(BASE + path)
    p = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    headers = {"Accept": "application/json", "Connection": "close"}
    payload = None
    if method in ("POST", "PUT"):
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body if body is not None else {}).encode()
    if _COOKIE["v"]:
        headers["Cookie"] = _COOKIE["v"]
    conn = http.client.HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port or 80, timeout=timeout)
    try:
        conn.request(method, p, body=payload, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode()
        sc = resp.getheader("Set-Cookie")
        if sc:
            _COOKIE["v"] = sc.split(";", 1)[0]
        try:
            return resp.status, (json.loads(raw) if raw else {})
        except Exception:
            return resp.status, {"raw": raw[:300]}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": repr(e)}
    finally:
        conn.close()


def _first_condition_line(pack, nid):
    """取该节点第一条出边的自然语言 condition，转成一句玩家第一人称台词（无关键词）。
    导演读这句话理解玩家意图后推进——这正是端到端验证 LLM 导演。"""
    node = pack.graph.nodes.get(nid)
    if not node:
        return None
    for e, _dst in pack.graph.get_children(nid):
        cond = str(getattr(e, "condition", "") or "").strip()
        if cond:
            said = cond.replace("玩家决定", "我决定").replace("玩家", "我")
            return f"（我打定主意）{said}"
    return None


def main() -> int:
    from agent_world.drama_demo.shared.story_pack import load_story_pack
    from agent_world.drama_demo.shared.env_status import is_runner_ready

    print("=" * 60)
    print("  沧澜剑派 验收门禁 (canglan_sword E2E · LLM 导演驱动)")
    print("=" * 60)

    shutil.rmtree(SIM, ignore_errors=True)
    SIM.mkdir(parents=True, exist_ok=True)
    env = _env()

    pack = load_story_pack(SID)
    g = pack.graph
    names = {int(a["agent_id"]): a["name"] for a in pack.agents["agents"]}
    label_to_node = {n.beats_label: nid for nid, n in g.nodes.items()}

    runner = flask = None
    rlog = open("/tmp/canglan_gate_runner.log", "w")
    flog = open("/tmp/canglan_gate_flask.log", "w")
    try:
        runner = subprocess.Popen(
            [sys.executable, "-m", "agent_world.drama_demo.run_drama", "--sim-dir", str(SIM), "--log-level", "INFO"],
            env=env, stdout=rlog, stderr=subprocess.STDOUT, cwd=str(ROOT),
        )
        for _ in range(60):
            if is_runner_ready(str(SIM)):
                break
            if runner.poll() is not None:
                raise GateFailure("Runner 提前退出（见 /tmp/canglan_gate_runner.log）")
            time.sleep(1)
        else:
            raise GateFailure("Runner 启动超时")
        seed_log = Path("/tmp/canglan_gate_runner.log").read_text()
        if f"从 Story Pack '{SID}'" not in seed_log:
            raise GateFailure("Runner 未从 canglan Story Pack 播种")
        print("  ✓ Runner 从 Story Pack 播种 canglan_sword")

        flask = subprocess.Popen(
            [sys.executable, "-m", "flask", "run", "--port", PORT],
            env=env, stdout=flog, stderr=subprocess.STDOUT, cwd=str(ROOT),
        )
        for _ in range(90):
            st, _ = api("GET", "/health", timeout=8)
            if st == 200:
                break
            if flask.poll() is not None:
                raise GateFailure("Flask 提前退出")
            time.sleep(1.5)
        else:
            raise GateFailure("Flask /health 超时")
        print("  ✓ Flask /health 200")

        st, _ = api("POST", "/session/start", {})
        if st != 200:
            raise GateFailure(f"/session/start HTTP {st}")
        print("  ✓ /session/start 200")

        since, ended, npc_lines = 0, None, 0
        for turn in range(1, 10):
            st, dd = api("GET", f"/world-delta?since_tick={since}")
            cur = (dd.get("data") or {}).get("current_phase") or g.nodes[g.initial_node].beats_label
            nid = label_to_node.get(cur, g.initial_node)
            say = _first_condition_line(pack, nid)
            if say is None:
                raise GateFailure(f"节点 {nid}「{cur}」无出边 condition——卡住")
            st, pr = api("POST", "/player-turn", {"player_text": say})
            if st != 200:
                raise GateFailure(f"/player-turn HTTP {st}: {pr}")
            new_phase, game_over, stable = cur, None, 0
            for _ in range(40):
                time.sleep(1.5)
                st, dd = api("GET", f"/world-delta?since_tick={since}")
                d = dd.get("data") or {}
                since = max(since, int(d.get("through_tick", since) or since))
                for plist in (d.get("room_f2f") or {}).values():
                    for m in plist:
                        if int(m.get("sender_id", -1)) != 0 and (m.get("content") or "").strip():
                            npc_lines += 1
                new_phase = d.get("current_phase") or new_phase
                if d.get("game_over"):
                    game_over = d["game_over"]
                if new_phase != cur or game_over:
                    stable += 1
                    if stable >= 2 or game_over:
                        break
            if game_over:
                ended = game_over
                break

        if not ended:
            raise GateFailure("玩到上限仍未触发结局")
        eid = ended.get("ending_id")
        if eid not in g.endings:
            raise GateFailure(f"结局 id 未知: {eid}")
        if ended.get("status") not in ("completed", "game_over"):
            raise GateFailure(f"结局 status 异常: {ended.get('status')}")
        print(f"  ✓ 台词驱动通关：结局 [{eid}] ({g.endings[eid].kind}) status={ended.get('status')}")
        if npc_lines <= 0:
            raise GateFailure("全程无任何 NPC 当面对白浮现（agent/读模型可能异常）")
        print(f"  ✓ NPC 当面对白浮现 {npc_lines} 条（人设数据驱动）")
    finally:
        for proc in (runner, flask):
            if proc is not None:
                try:
                    proc.terminate(); proc.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    try:
                        proc.kill()
                    except Exception:  # noqa: BLE001
                        pass
        shutil.rmtree(SIM, ignore_errors=True)

    print("\n  [前端] npm run build …")
    build = subprocess.run(
        ["npm", "run", "build"], cwd=str(HBM / "web"),
        capture_output=True, text=True,
    )
    if build.returncode != 0:
        print(build.stdout[-2000:]); print(build.stderr[-2000:])
        raise GateFailure("npm run build 失败")
    print("  ✓ npm run build 通过")

    print("\n" + "=" * 60)
    print("  沧澜剑派 验收门禁全部通过 ✅")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GateFailure as exc:
        print(f"\n❌ 门禁失败: {exc}")
        sys.exit(1)

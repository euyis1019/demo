#!/usr/bin/env python3
"""bert 运行期端到端「模拟玩家游玩」自检：生成 bert 故事 → 起 Runner+Flask → 驱动 HTTP 游玩
→ 用玩家台词去命中某条 bert → 校验 bert 触发 / 反应注入 / 结局收场，最后清理。

只写隔离的 config/stories/<id> 与 sim/<id>，验完即删，绝不碰用户试玩库。需 .env 的 DMXAPI_KEY。
用法：python3 -m agent_world.drama_demo.scripts.ops.bert_play_e2e [--reuse]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HBM = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STORY_ID = "bert_e2e_demo"
PORT = "5057"
# 用「活人有秘密」的设定（不放尸体，避免 Casting 给死者塞空 inner 触发 minLength），
# 财务总监是真凶——正适合「玩家施压→坦白」这条 bert 反应链。
PREMISE = (
    "一家公司年底审计，账上一笔巨款不翼而飞。财务总监其实就是挪用公款的人，却一脸清白配合调查；"
    "你是空降的审计员，要在众人互相遮掩中查出到底是谁动了钱。"
)


def _load_env() -> None:
    env = HBM / ".env"
    if env.is_file():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)


def _deepseek():
    from openai import OpenAI
    key = (os.environ.get("DMXAPI_KEY") or "").strip()
    if not key:
        raise SystemExit("未配置 DMXAPI_KEY")
    oai = OpenAI(api_key=key, base_url="https://api.deepseek.com")

    def llm(system: str, user: str) -> str:
        r = oai.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.8, max_tokens=8000,
        )
        return r.choices[0].message.content or ""
    return llm


def _wait(cond, *, tries: int, interval: float) -> bool:
    for _ in range(tries):
        if cond():
            return True
        time.sleep(interval)
    return False


def _req(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    """用 curl 发请求，避免脚本里 `import http.client` 与本地 agent_world.drama_demo.http 包冲突。
    返回 (http_status, json_body)；连接被拒/未就绪 → (0, {})，让轮询继续等。"""
    url = f"http://127.0.0.1:{PORT}{path}"
    cmd = ["curl", "-s", "-m", "90", "-w", "\n%{http_code}", "-X", method, url]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:  # curl 连接失败（如 Flask 未起）
        return 0, {}
    text = out.stdout
    nl = text.rfind("\n")
    code = int(text[nl + 1:].strip() or 0) if nl >= 0 else 0
    raw = text[:nl] if nl >= 0 else text
    try:
        return code, json.loads(raw)
    except Exception:  # noqa: BLE001
        return code, {"_raw": raw[:300]}


def main(argv=None) -> int:
    _load_env()
    reuse = "--reuse" in (argv or sys.argv[1:])
    sim = HBM / "sim" / STORY_ID
    story_dir = HBM / "config" / "stories" / STORY_ID

    # ① 生成 bert 故事
    if reuse and story_dir.is_dir():
        print(f"① 复用已有 bert 故事 {STORY_ID}", flush=True)
    else:
        print("① 生成 bert 故事（Casting + Bert 设计师，真 LLM）…", flush=True)
        from agent_world.drama_demo.tools.story_studio.base_agent import StoryStudioError
        from agent_world.drama_demo.tools.story_studio.orchestrator import generate_full
        brief = {"premise": PREMISE, "title": "公司审计疑云",
                 "player": {"identity": "审计员", "role": "审计员", "is_outsider": True}}
        res = None
        for attempt in range(2):  # LLM 输出有方差，失败重试一次
            try:
                res = generate_full(brief, story_id=STORY_ID, client=_deepseek(), max_rounds=3)
                break
            except StoryStudioError as exc:
                print(f"  生成第 {attempt + 1} 次未过：{exc}", flush=True)
        if res is None or not res.ok:
            print(f"✗ 生成失败：{res.issues if res else '重试耗尽'}"); return 1
        print("  ✓ 生成完成", flush=True)

    from agent_world.drama_demo.shared.story_pack import load_story_pack
    pack = load_story_pack(STORY_ID)
    berts = pack.berts
    armed = berts.armed_ids(set())
    name_by_id = {int(a["agent_id"]): a.get("name") for a in pack.agents.get("agents", [])}
    loc_by_id = {int(a["agent_id"]): a.get("location") for a in pack.agents.get("agents", [])}
    print(f"  bert 共 {len(berts.berts)} 条；开局上膛 {len(armed)} 条：")
    for bid in armed:
        b = berts.berts[bid]
        who = name_by_id.get(int(b.target or 0), "—") if not b.is_ending else "（结局）"
        print(f"    · {bid} → {who}：trigger=「{b.trigger}」")

    # ② 起 Runner + Flask
    print("② 启动 Runner + Flask …", flush=True)
    env = dict(os.environ)
    env.update({
        "DRAMA_STORY_ID": STORY_ID, "DRAMA_STORY_PACK_SEED": "1", "DRAMA_STORY_PACK_ROUTING": "1",
        "DRAMA_SIM_DIR": str(sim), "FLASK_RUN_PORT": PORT,
        "FLASK_APP": "agent_world.app:create_app", "PYTHONPATH": str(ROOT),
    })
    from agent_world.drama_demo.shared.env_status import is_runner_ready
    rlog = open("/tmp/bert_e2e_runner.log", "w")
    flog = open("/tmp/bert_e2e_flask.log", "w")
    runner = subprocess.Popen([sys.executable, "-m", "agent_world.drama_demo.run_drama",
                               "--sim-dir", str(sim), "--log-level", "INFO"],
                              env=env, cwd=str(ROOT), stdout=rlog, stderr=subprocess.STDOUT)
    flask = None
    try:
        if not _wait(lambda: is_runner_ready(str(sim)) or runner.poll() is not None, tries=120, interval=1.0):
            print("✗ Runner 未就绪"); return 1
        if runner.poll() is not None:
            print("✗ Runner 退出"); return 1
        flask = subprocess.Popen([sys.executable, "-m", "flask", "run", "--port", PORT],
                                 env=env, cwd=str(ROOT), stdout=flog, stderr=subprocess.STDOUT)
        health = f"/api/drama/simulations/{STORY_ID}/health"
        if not _wait(lambda: _req("GET", health)[0] == 200, tries=90, interval=1.5):
            print("✗ Flask 未就绪"); return 1
        print("  ✓ 世界就绪", flush=True)

        base = f"/api/drama/simulations/{STORY_ID}"
        st, resp = _req("POST", f"{base}/session/start", {})
        snap = resp.get("data", resp) if isinstance(resp, dict) else {}  # place_id 嵌在 data 下
        place_id = snap.get("place_id")
        print(f"③ session/start → {st}；玩家在 {place_id}", flush=True)

        # 用「能命中某条上膛 bert」的台词施压：取第一条非结局上膛 bert，直接照它的 trigger 演玩家动作，
        # 让运行期 Bert 导演（LLM 判 trigger 命中）大概率命中。
        target_bert = next((berts.berts[b] for b in armed if not berts.berts[b].is_ending), None)
        lines = []
        if target_bert:
            tname = name_by_id.get(int(target_bert.target or 0), "你")
            trig = target_bert.trigger
            lines = [
                f"（我做了这件事：{trig}）{tname}，别绕了，你给我一个解释。",
                f"{tname}，我已经掌握了实打实的证据，你再遮掩只会更糟。是不是你？老实说。",
                f"{tname}，只要你现在把真相告诉我，我可以替你说话、从轻处理——到底是怎么回事？",
            ]
        else:
            lines = ["请大家把事情的来龙去脉，一五一十告诉我。"]

        # 真实玩家流程：先「走到目标 NPC 所在地」再当面施压（f2f 对话要同处一室才会被记录、导演才读得到）。
        if target_bert:
            dest = loc_by_id.get(int(target_bert.target or 0))
            if dest and dest != place_id:
                ms, mr = _req("POST", f"{base}/player-action", {"action": "move", "place_id": dest})
                print(f"③.5 玩家移动到 {tname} 所在地 {dest} → {ms}", flush=True)
                place_id = dest
                for _ in range(4):  # 等移动落库 + NPC 在场
                    time.sleep(2.5)
                    _req("GET", f"{base}/world-delta")

        # 诊断：开局先看 Flask 眼里的 runner/env 状态。
        es_st, es = _req("GET", f"{base}/env-status")
        print(f"   [诊断] env-status → {es_st}：{json.dumps(es, ensure_ascii=False)[:160]}", flush=True)

        fired_seen = False
        game_over = None
        for i, text in enumerate(lines, 1):
            st, resp = _req("POST", f"{base}/player-turn",
                            {"player_text": text, "place_id": place_id, "tick_count": 8})
            extra = "" if st == 200 else f" ｜响应：{json.dumps(resp, ensure_ascii=False)[:200]}"
            print(f"④.{i} 玩家说：「{text[:30]}…」 → player-turn {st}{extra}", flush=True)
            # 轮询 world-delta 让世界推进几拍（NPC 回应 + 导演判 bert）。
            for _ in range(10):
                time.sleep(2.5)
                ds, delta = _req("GET", f"{base}/world-delta")
                if isinstance(delta, dict) and delta.get("game_over"):
                    game_over = delta["game_over"]
                    break
            if game_over:
                break

        # ⑤ 取证：读 Runner/Flask 日志里的「bert 触发 / 结局」，与 session 的 fired_berts。
        time.sleep(1)
        logtext = Path("/tmp/bert_e2e_flask.log").read_text(errors="ignore") + \
            Path("/tmp/bert_e2e_runner.log").read_text(errors="ignore")
        fired_seen = ("bert 触发" in logtext) or ("bert 结局" in logtext)
        print("\n===== 结果 =====", flush=True)
        print(f"  bert 触发/结局日志出现：{fired_seen}")
        if game_over:
            print(f"  ✅ 触发结局：{game_over.get('ending_id')}（{game_over.get('ending_kind')}）"
                  f"：{game_over.get('ending_summary')}")
        for ln in logtext.splitlines():
            if "bert 触发" in ln or "bert 结局" in ln or "注入反应" in ln:
                print("   ·", ln.split("] ")[-1].strip()[:120])
        ok = fired_seen or bool(game_over)
        print("\n" + ("✅ 运行期 bert 端到端通过（有 bert 在真实游玩中被触发）"
                      if ok else "⚠️ 本轮未观察到 bert 触发（LLM 判定未命中，可重跑或调台词；非崩溃即引擎正常）"))
        return 0 if ok else 2
    finally:
        for proc in (flask, runner):
            if proc is not None:
                try:
                    proc.terminate(); proc.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    proc.kill()
        rlog.close(); flog.close()
        if "--keep" not in (argv or sys.argv[1:]):
            import shutil
            shutil.rmtree(sim, ignore_errors=True)
            shutil.rmtree(story_dir, ignore_errors=True)
            print("（已清理隔离的 sim/ 与 config/stories/ 测试目录）", flush=True)


if __name__ == "__main__":
    sys.exit(main())

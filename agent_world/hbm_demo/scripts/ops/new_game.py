#!/usr/bin/env python3
"""一键开新游戏：玩家给个大概剧情 → 自动设计 Story Pack → 启动后台世界(Runner) + Flask，即可开玩。

用法：
    python3 -m agent_world.hbm_demo.scripts.ops.new_game --premise "一句话剧情概要"
    python3 -m agent_world.hbm_demo.scripts.ops.new_game --premise "..." --assets       # 同时出图
    python3 -m agent_world.hbm_demo.scripts.ops.new_game --premise "..." --smoke         # 自检后退出(测试)

依赖 .env：DMXAPI_KEY(设计剧情用 DeepSeek) + 可选 ARK_API_KEY(出图用 Seedream)。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HBM = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    env = HBM / ".env"
    if env.is_file():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)


def _slug(premise: str) -> str:
    base = re.sub(r"[^0-9a-zA-Z一-鿿]+", "_", premise.strip())[:16].strip("_") or "story"
    return f"{base}_{int(time.time()) % 100000}"


def _deepseek_client():
    from openai import OpenAI

    key = (os.environ.get("DMXAPI_KEY") or "").strip()
    if not key:
        raise SystemExit("未配置 DMXAPI_KEY（设计剧情需要）。请在 agent_world/hbm_demo/.env 设置 DMXAPI_KEY=...")
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


def main(argv=None) -> int:
    _load_env()
    p = argparse.ArgumentParser(description="给个大概剧情，自动设计并启动后台世界")
    p.add_argument("--premise", required=True, help="一句话/一段大概的剧情")
    p.add_argument("--player", default="一名卷入其中的外来者", help="玩家身份")
    p.add_argument("--title", default=None, help="标题(默认取自 premise)")
    p.add_argument("--story-id", default=None)
    p.add_argument("--acts", type=int, default=4, help="目标幕数")
    p.add_argument("--assets", action="store_true", help="同时用文生图出全套图(Seedream)")
    p.add_argument("--port", default="5000")
    p.add_argument("--reuse", action="store_true", help="复用已有的同名 Story Pack（跳过设计，直接起世界）")
    p.add_argument("--smoke", action="store_true", help="启动并自检健康后退出(测试用)")
    args = p.parse_args(argv)

    story_id = args.story_id or _slug(args.premise)
    sys.path.insert(0, str(ROOT))

    if args.reuse and (HBM / "config" / "stories" / story_id).is_dir():
        print(f"① 复用已有 Story Pack：{story_id}（跳过设计）", flush=True)
    else:
        # ① 设计剧情：Designer→Casting→Writer→validate
        print(f"① 设计剧情中（Designer→Casting→Writer）…  story_id={story_id}", flush=True)
        brief = {
            "premise": args.premise,
            "title": args.title or args.premise[:24],
            "player": {"identity": args.player, "role": args.player, "is_outsider": True},
            "target_acts": int(args.acts),
            "target_nodes": str(max(args.acts, 4)),
        }
        from agent_world.hbm_demo.tools.story_studio.orchestrator import generate_full

        res = generate_full(brief, story_id=story_id, client=_deepseek_client(), max_rounds=3)
        if not res.ok:
            print(f"✗ 剧情设计失败：{res.issues}")
            return 1
        print(f"  ✓ Story Pack 已生成 → config/stories/{story_id}/", flush=True)

    # ② 可选：出图
    if args.assets:
        print("② 出图中（Seedream，能生成即可，无视觉复核）…", flush=True)
        from agent_world.hbm_demo.tools.story_studio.artist_runner import generate_story_assets
        from agent_world.hbm_demo.tools.story_studio.image_client import ImageKeyMissing

        try:
            rep = generate_story_assets(story_id)
            print(f"  图片：已就位 {rep.present}/{rep.required}" + ("（足够）" if rep.enough else f"（缺 {len(rep.missing)}，可重跑补齐）"))
        except ImageKeyMissing as exc:
            print(f"  ⚠️ 跳过出图：{exc}")

    # ③ 启动后台世界（Runner 播种 + 世界循环）+ Flask
    print("③ 启动后台世界（Runner）+ Flask …", flush=True)
    import subprocess

    sim = HBM / "sim" / story_id
    env = dict(os.environ)
    env.update({
        "HBM_STORY_ID": story_id, "HBM_STORY_PACK_SEED": "1", "HBM_STORY_PACK_ROUTING": "1",
        "HBM_SIM_DIR": str(sim), "FLASK_RUN_PORT": str(args.port),
        "FLASK_APP": "agent_world.app:create_app", "PYTHONPATH": str(ROOT),
    })
    from agent_world.hbm_demo.shared.env_status import is_runner_ready

    runner = subprocess.Popen(
        [sys.executable, "-m", "agent_world.hbm_demo.run_hbm", "--sim-dir", str(sim), "--log-level", "INFO"],
        env=env, cwd=str(ROOT),
    )
    if not _wait(lambda: is_runner_ready(str(sim)) or runner.poll() is not None, tries=90, interval=1.0) or runner.poll() is not None:
        print("✗ Runner 启动失败"); runner.terminate(); return 1
    flask = subprocess.Popen([sys.executable, "-m", "flask", "run", "--port", str(args.port)], env=env, cwd=str(ROOT))

    import http.client

    health_path = f"/api/hbm/simulations/{story_id}/health"

    def _healthy() -> bool:
        # werkzeug 开发服务器对 keep-alive 易报 RemoteDisconnected——用 http.client + Connection: close
        conn = http.client.HTTPConnection("127.0.0.1", int(args.port), timeout=8)
        try:
            conn.request("GET", health_path, headers={"Accept": "application/json", "Connection": "close"})
            return conn.getresponse().status == 200
        except Exception:  # noqa: BLE001
            return False
        finally:
            conn.close()

    ok = _wait(_healthy, tries=90, interval=1.5)
    base = f"http://127.0.0.1:{args.port}/api/hbm/simulations/{story_id}"
    print("\n" + "=" * 60)
    if ok:
        print(f"  ✅ 世界已就绪！后台世界正在运行。")
        print(f"  · 浏览器开玩前端：cd agent_world/hbm_demo/web && npm run dev")
        print(f"  · 或直接调 API：{base}/session/start  →  {base}/player-turn  →  {base}/world-delta")
    else:
        print("  ✗ Flask 未就绪")
    print("=" * 60, flush=True)

    if args.smoke or not ok:
        for proc in (runner, flask):
            try:
                proc.terminate(); proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                proc.kill()
        return 0 if ok else 1

    print("（按 Ctrl+C 停止世界）", flush=True)
    try:
        runner.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for proc in (runner, flask):
            try:
                proc.terminate(); proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())

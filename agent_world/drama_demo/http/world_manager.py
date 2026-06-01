"""WorldManager —— Flask 侧的「大厅/世界生命周期」管理（单进程 dev server，进程内单例）。

职责：
- 列出已有故事；
- 从玩家输入的一段剧情**异步**生成完整 Story Pack（Designer→Casting→Writer）+ 可选出图（Seedream），
  用 job 跟踪进度；
- **激活**某个故事 = 确保有一个 Runner 子进程在为它播种世界、跑世界循环（按故事起/重启），
  并把它设为「当前故事」（get_sim_dir / sim_id 放行据此切换）。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("agent_world.drama_demo.world_manager")

_HBM = Path(__file__).resolve().parents[1]
_ROOT = Path(__file__).resolve().parents[3]


def _deepseek_client():
    """设计期 LLM 客户端——加 response_format=json_object 提升 JSON 健壮性（审计 K），
    其余保留经验证可用的参数（0.8 创意温度 + max_tokens=8000 + 600s 超时）。"""
    from openai import OpenAI

    key = (os.environ.get("DMXAPI_KEY") or "").strip()
    if not key:
        raise RuntimeError("未配置 DMXAPI_KEY（设计剧情需要）。请在 agent_world/drama_demo/.env 设置。")
    oai = OpenAI(api_key=key, base_url="https://api.deepseek.com", timeout=600.0)

    def llm(system: str, user: str) -> str:
        r = oai.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.8, max_tokens=8000,
            response_format={"type": "json_object"},
        )
        return r.choices[0].message.content or ""

    return llm


class WorldManager:
    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._story: Optional[str] = None
        self._lock = threading.Lock()
        self.jobs: Dict[str, Dict[str, Any]] = {}

    # ---------- 列故事 ----------
    def list_stories(self) -> List[Dict[str, Any]]:
        from agent_world.drama_demo.shared.prompt_paths import story_dir
        from agent_world.drama_demo.shared.story_pack import list_story_ids, load_story_pack

        out: List[Dict[str, Any]] = []
        for sid in list_story_ids():
            try:
                pack = load_story_pack(sid)
                title = str((pack.meta or {}).get("title") or sid)
                cover = story_dir(sid) / "assets" / "cover.png"
                out.append({
                    "story_id": sid,
                    "title": title[:40],
                    "has_assets": cover.is_file(),
                    "agents": len([a for a in pack.agents.get("agents", []) if int(a.get("agent_id", -1)) > 0]),
                })
            except Exception as exc:  # noqa: BLE001
                log.warning("list_stories skip %s: %s", sid, exc)
        return out

    # ---------- 建故事（异步生成）----------
    def create_story(self, *, premise: str, player: str = "一名卷入其中的外来者",
                     title: Optional[str] = None, acts: int = 4, with_assets: bool = True) -> str:
        job_id = uuid.uuid4().hex[:12]
        # 轻量内存护栏：只保留最近若干条 job（淘汰最早的已完成态），避免长跑 dev server 单调膨胀。
        if len(self.jobs) >= 40:
            done = [k for k, v in list(self.jobs.items()) if v.get("status") in ("done", "error")]
            for k in done[: max(0, len(self.jobs) - 30)]:
                self.jobs.pop(k, None)
        self.jobs[job_id] = {"status": "running", "step": "排队中", "story_id": None, "error": None}
        t = threading.Thread(
            target=self._generate,
            kwargs=dict(job_id=job_id, premise=premise, player=player, title=title, acts=acts, with_assets=with_assets),
            daemon=True,
        )
        t.start()
        return job_id

    def _generate(self, *, job_id: str, premise: str, player: str, title: Optional[str], acts: int, with_assets: bool) -> None:
        job = self.jobs[job_id]
        try:
            from agent_world.drama_demo.tools.story_studio.naming import slug_story_id

            story_id = slug_story_id(premise)
            job.update(story_id=story_id, step="设计剧情（Designer→Casting→Writer）…")
            brief = {
                "premise": premise,
                "title": title or premise[:24],
                "player": {"identity": player, "role": player, "is_outsider": True},
                # 任务式生成：acts 即任务链长度（保留 target_acts/target_nodes 兼容旧词）。
                "target_tasks": int(acts),
                "target_acts": int(acts),
                "target_nodes": str(max(int(acts), 4)),
            }
            from agent_world.drama_demo.tools.story_studio.orchestrator import generate_full

            # generate_full 成功才返回（校验通不过会 raise StoryStudioError，落到外层 except）。
            generate_full(brief, story_id=story_id, client=_deepseek_client(), max_rounds=3)
            if with_assets:
                job["step"] = "准备图片资源（Seedream）…"
                try:
                    from agent_world.drama_demo.tools.story_studio.artist_runner import generate_story_assets
                    from agent_world.drama_demo.tools.story_studio.image_client import ImageKeyMissing

                    try:
                        rep = generate_story_assets(story_id)
                        job["assets"] = f"{rep.present}/{rep.required}"
                    except ImageKeyMissing:
                        job["assets"] = "跳过（未配置文生图 key）"
                except Exception as exc:  # noqa: BLE001
                    job["assets"] = f"出图出错：{exc}"
            job.update(status="done", step="准备完成，可以开玩")
        except Exception as exc:  # noqa: BLE001
            log.exception("generate story failed")
            job.update(status="error", step="生成失败", error=str(exc))

    # ---------- 激活（起世界）----------
    def is_active(self, story_id: str) -> bool:
        return self._story == story_id and self._proc is not None and self._proc.poll() is None

    def activate(self, story_id: str, *, timeout_s: float = 90.0) -> bool:
        from agent_world.drama_demo.shared.env_status import is_runner_ready
        from agent_world.drama_demo.shared.story_pack import list_story_ids

        if story_id not in list_story_ids():
            raise ValueError(f"未知故事：{story_id}")
        with self._lock:
            if self.is_active(story_id):
                return True
            self._stop_locked()
            sim = _HBM / "sim" / story_id
            # 清掉上一轮可能残留的就绪标记（被 SIGKILL/崩溃留下的 stale status=running），
            # 否则就绪等待会在新 Runner 还没写 starting 之前就读到旧 running 而误判已就绪。
            try:
                (sim / "env_status.json").unlink(missing_ok=True)
            except OSError:
                pass
            env = dict(os.environ)
            env.update({
                "DRAMA_STORY_ID": story_id, "DRAMA_STORY_PACK_SEED": "1", "DRAMA_STORY_PACK_ROUTING": "1",
                "DRAMA_SIM_DIR": str(sim), "PYTHONPATH": str(_ROOT),
            })
            self._proc = subprocess.Popen(
                [sys.executable, "-m", "agent_world.drama_demo.run_drama", "--sim-dir", str(sim), "--log-level", "INFO"],
                env=env, cwd=str(_ROOT),
            )
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                if is_runner_ready(str(sim)):
                    break
                if self._proc.poll() is not None:
                    raise RuntimeError("Runner 启动即退出")
                time.sleep(1.0)
            ready = is_runner_ready(str(sim))
            if ready:
                self._story = story_id
                self._set_active(story_id)
                log.info("activated story %s (runner pid=%s)", story_id, self._proc.pid)
            else:
                # 新故事没能就绪：上一个故事的 Runner 已被停掉，这里把半死的新 Runner 也清掉、
                # 把当前故事指针置空，避免留下「_story 指向旧故事但其 Runner 已死」的不一致态
                # （否则玩家退回旧故事时 is_active 会误判它仍活着）。前端拿到 ready=False 留在大厅。
                self._stop_locked()
                self._story = None
                log.warning("activate %s failed: runner not ready within %.0fs", story_id, timeout_s)
            return ready

    def _set_active(self, story_id: str) -> None:
        from agent_world.drama_demo.features.f01_session.paths import clear_scenario_cache
        from agent_world.drama_demo.shared import active_game, story_config

        active_game.set_active_story(story_id)
        clear_scenario_cache()
        story_config.clear_pack_cache()

    def _stop_locked(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate(); self._proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                try:
                    self._proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        self._proc = None

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()


WORLD_MANAGER = WorldManager()

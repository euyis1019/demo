"""运行期「当前在玩哪个故事」的可变状态。

默认从 env DRAMA_STORY_ID（默认 canglan_sword）。前端选/建故事后，由 WorldManager 调
set_active_story() 切换；get_sim_dir / active_story_id / sim_id 放行都读这里。纯状态，
不 import features（D3）；切换故事时的缓存清理由 L3(WorldManager) 负责。
"""

from __future__ import annotations

import os
from pathlib import Path

_DRAMA_ROOT = Path(__file__).resolve().parents[1]
_state: dict = {"story": None}


def _env_default() -> str:
    return (os.environ.get("DRAMA_STORY_ID") or "canglan_sword").strip() or "canglan_sword"


def get_active_story() -> str:
    return _state["story"] or _env_default()


def set_active_story(story_id: str) -> None:
    sid = str(story_id or "").strip()
    if sid:
        _state["story"] = sid


def active_sim_dir() -> Path:
    """当前故事的 sim 目录。

    优先级：
      1. 运行期已激活的故事（_state['story']，只有 Flask 大厅路径会调 set_active_story）；
      2. env DRAMA_SIM_DIR（Runner 子进程由 WorldManager 显式注入，用来锁定自己那份 sim）；
      3. 默认故事。
    关键点：Flask 进程启动时常会继承到 DRAMA_SIM_DIR（start_demo.sh / new_game.py 会导出），
    一旦大厅激活了某故事，读路径必须跟着切到 sim/<story>，不能再被旧 env 钉死读到别的世界。
    Runner 子进程从不调 set_active_story（_state['story'] 恒为 None），仍走自己的 DRAMA_SIM_DIR。
    """
    if _state["story"]:
        return (_DRAMA_ROOT / "sim" / _state["story"]).resolve()
    env = os.environ.get("DRAMA_SIM_DIR")
    if env:
        return Path(env).resolve()
    return (_DRAMA_ROOT / "sim" / get_active_story()).resolve()

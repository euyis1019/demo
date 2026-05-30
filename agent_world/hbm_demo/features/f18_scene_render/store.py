"""帧跨进程中转：Runner 写、Flask 读（经文件系统，因两者是独立进程）。

存 base64 文本(latest.b64) + 元信息(latest.json)，避免在 world.db 里堆 base64。
两个文件都用原子写（tempfile + os.replace），防 Flask 读到写一半（红线：原子写）。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple


def frames_dir(sim_dir) -> Path:
    return Path(sim_dir) / "frames"


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_latest_frame(sim_dir, tick: int, image_b64: str, mime: str) -> None:
    """Runner 侧：写入最新帧（覆盖 latest，不按 tick 堆文件，避免无限增长）。"""
    d = frames_dir(sim_dir)
    _atomic_write_bytes(d / "latest.b64", (image_b64 or "").encode("ascii"))
    meta = {"tick": int(tick), "mime": mime, "len": len(image_b64 or "")}
    _atomic_write_bytes(d / "latest.json", json.dumps(meta).encode("utf-8"))


def read_latest_meta(sim_dir) -> Optional[dict]:
    p = frames_dir(sim_dir) / "latest.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def read_latest_frame_data_uri(sim_dir, since_tick: int = -1) -> Optional[Tuple[int, str]]:
    """Flask 侧：若最新帧 tick > since_tick，返回 (tick, data_uri)；否则 None。"""
    meta = read_latest_meta(sim_dir)
    if not meta:
        return None
    tick = int(meta.get("tick", -1))
    if tick <= int(since_tick):
        return None
    b64_path = frames_dir(sim_dir) / "latest.b64"
    if not b64_path.is_file():
        return None
    try:
        b64 = b64_path.read_text(encoding="ascii")
    except OSError:
        return None
    mime = str(meta.get("mime") or "image/jpeg")
    return tick, f"data:{mime};base64,{b64}"


def clear_frames(sim_dir) -> None:
    """会话重置时清掉旧帧，避免显示上一局的画面。"""
    d = frames_dir(sim_dir)
    for name in ("latest.b64", "latest.json"):
        try:
            (d / name).unlink()
        except OSError:
            pass

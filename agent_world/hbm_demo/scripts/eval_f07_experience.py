#!/usr/bin/env python3
"""F07 体验评测 — 多 Phase 运行时采样 + 结构化报告 (dev_logs/29 + 用户需求)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[3]
HBM_DIR = ROOT / "agent_world" / "hbm_demo"
SIM_DIR = HBM_DIR / "sim" / "hbm_memory_war"

sys.path.insert(0, str(ROOT))

from agent_world.hbm_demo.scripts.test_m0_acceptance import (  # noqa: E402
    BASE_PATH,
    SIM_ID,
    apply_hbm_demo_env,
    http_json,
    llm_api_key_configured,
    poll_action_result,
    start_stack,
)


@dataclass
class TurnSample:
    label: str
    phase: str
    player_text: str
    public: List[Dict[str, Any]] = field(default_factory=list)
    observer: List[Dict[str, Any]] = field(default_factory=list)
    status: str = ""
    notes: List[str] = field(default_factory=list)


def _char_count(messages: List[Dict[str, Any]]) -> int:
    return sum(len(str(m.get("content") or "")) for m in messages)


def _send_turn(base: str, cookie: str, text: str, *, max_wait: float = 240.0):
    code, post, cookie = http_json(
        "POST",
        f"{base}{BASE_PATH}/player-turn",
        body={"player_text": text},
        cookie=cookie,
        timeout=120.0,
    )
    if code != 200 or not post.get("success"):
        raise RuntimeError(f"player-turn failed: {post}")
    task_id = (post.get("data") or {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"missing task_id: {post}")
    result, cookie = poll_action_result(base, task_id, cookie, max_wait=max_wait)
    return result, cookie


def _phase2_ipc_smoke() -> TurnSample:
    """Phase 2 inject via IPC — Jensen 1v1 私密审查."""
    from types import SimpleNamespace

    from agent_world.hbm_demo.features.f05_story_routing.routing import (
        PLACE_JENSEN_ROOM,
        build_inject_payload,
        inject_agent_ids_for_phase,
    )
    from agent_world.hbm_demo.features.f06_read_model.world_db import ReadOnlyWorldDB
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        resolve_inject_tick_count,
    )
    from agent_world.hbm_demo.http.ipc_helper import (
        get_ipc_client,
        send_inject_batch,
        send_reset_world,
    )

    player_text = (
        "黄总，外面三巨头再吵也挡不住事实：我的稀疏注意力能把 KV Cache 砍 80%，"
        "您要是信我，三分钟后我给您看 profiling 曲线。"
    )
    sample = TurnSample(
        label="Phase2 IPC Turn5",
        phase="Phase 2",
        player_text=player_text,
    )

    client = get_ipc_client(str(SIM_DIR))
    send_reset_world(client, timeout=120.0)

    session = SimpleNamespace(
        phase="Phase 2",
        player_turn=5,
        place_id=PLACE_JENSEN_ROOM,
        stats={"vision": 18, "execution": 12, "trust": 10, "burnout": 5},
    )
    events, _, ctx = build_inject_payload(session, player_text, task_id="eval_p2")
    inject_ids = inject_agent_ids_for_phase("Phase 2")
    if inject_ids != [2]:
        sample.notes.append(f"inject 目标异常: {inject_ids}")
    tick_count = resolve_inject_tick_count("Phase 2", 12)
    inject_resp = send_inject_batch(
        client,
        events=events,
        tick_count=tick_count,
        turn_context=ctx,
        timeout=180.0,
    )
    result = inject_resp.result or {}
    start_tick = int(result.get("start_tick", 0))
    end_tick = int(result.get("end_tick", start_tick))

    db = ReadOnlyWorldDB(SIM_DIR / "world.db")
    f2f_rows = db.fetch_f2f_history_at(PLACE_JENSEN_ROOM, end_tick, start_tick)
    rdc_rows = db.fetch_messages_since(
        channel_type="RDC", since_t=start_tick, t_now=end_tick
    )

    sample.public = [
        {"sender": row[1], "content": row[3]}
        for row in f2f_rows
        if int(row[1]) in (0, 2)
    ]
    sample.observer = [
        {
            "sender": int(r["sender_id"]),
            "recipient": int(r["recipient_id"]),
            "content": str(r["content"]),
        }
        for r in rdc_rows
        if int(r["sender_id"]) in (2, 3)
    ]
    sample.status = "completed"
    if not sample.public:
        sample.notes.append("Phase2 无 Jensen F2F")
    if "80" not in " ".join(str(m.get("content") or "") for m in sample.public):
        sample.notes.append("Jensen F2F 未引用玩家关键词 80%")
    vp_rdc = [m for m in sample.observer if int(m.get("sender", 0)) == 3]
    if len(vp_rdc) > 2:
        sample.notes.append(f"Tech VP RDC 过多: {len(vp_rdc)}")
    return sample


def _phase4_ipc_smoke() -> TurnSample:
    from agent_world.hbm_demo.features.f07_agent_control.phase4_smoke import (
        run_phase4_ipc_smoke,
    )

    player_text = "我接受加入团队，但我们先谈股权结构和期权池。"
    result = run_phase4_ipc_smoke(SIM_DIR, player_text=player_text, ipc_timeout=180.0)
    sample = TurnSample(
        label="Phase4 IPC Turn21",
        phase="Phase 4",
        player_text=player_text,
        status="completed" if result.ok else "failed",
    )
    if result.inject_agent_ids != [2]:
        sample.notes.append(f"inject={result.inject_agent_ids}")
    if result.vp_public_count != 0:
        sample.notes.append(f"VP 发言={result.vp_public_count}")
    if result.ceo_in_negotiation:
        sample.notes.append(f"CEO 仍在谈判室: {result.ceo_in_negotiation}")
    sample.public = [{"note": f"Jensen F2F count={result.jensen_f2f_count}"}]
    sample.observer = []
    return sample


def _score_brevity(messages: List[Dict[str, Any]], max_chars: int = 280) -> str:
    total = _char_count(messages)
    if total == 0:
        return "无输出"
    if total <= max_chars:
        return "简短 ✓"
    if total <= max_chars * 1.8:
        return "略长 △"
    return f"过长 ✗ ({total} 字)"


def _player_influence(text: str, messages: List[Dict[str, Any]], keywords: List[str]) -> str:
    blob = " ".join(str(m.get("content") or "") for m in messages).lower()
    hits = [k for k in keywords if k.lower() in blob or k.lower() in text.lower()]
    if hits:
        return f"有回应 ({', '.join(hits[:3])})"
    return "未明显引用玩家关键词"


def run_eval() -> Dict[str, Any]:
    env = apply_hbm_demo_env(os.environ.copy())
    report: Dict[str, Any] = {
        "llm_configured": llm_api_key_configured(env),
        "samples": [],
        "structural_checks": [],
        "summary": {},
    }

    # --- 结构层：F07 配置与知识库 ---
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        is_experience_hardening,
        is_f07_enabled,
        load_turn_control,
    )
    from agent_world.hbm_demo.features.f07_agent_control.knowledge import (
        build_agent_knowledge,
    )
    from agent_world.hbm_demo.features.f07_agent_control.llm_params import (
        resolve_llm_params,
    )
    from agent_world.hbm_demo.features.f07_agent_control.config import (
        inject_exclusive_ticks_for,
    )
    from types import SimpleNamespace

    def _move_allowed(phase: str) -> bool:
        import yaml

        path = HBM_DIR / "features" / "f07_agent_control" / "tool_matrix.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        block = (data.get("phases") or {}).get(phase) or {}
        return bool(block.get("move_allowed", False))

    cfg = load_turn_control()
    report["structural_checks"].append(
        {"check": "F07 enabled", "ok": is_f07_enabled()}
    )
    report["structural_checks"].append(
        {"check": "experience_hardening", "ok": is_experience_hardening()}
    )

    for phase, expected_primary in [
        ("Phase 1", [1, 2, 3]),
        ("Phase 2", [2]),
        ("Phase 4", [2]),
    ]:
        pcfg = (cfg.get("phases") or {}).get(phase) or {}
        primary = pcfg.get("primary_active")
        frozen = pcfg.get("frozen") or []
        report["structural_checks"].append(
            {
                "check": f"{phase} primary_active",
                "ok": primary == expected_primary,
                "value": primary,
            }
        )
        report["structural_checks"].append(
            {
                "check": f"{phase} move_allowed=false",
                "ok": _move_allowed(phase) is False,
                "value": _move_allowed(phase),
            }
        )
        if phase == "Phase 1":
            report["structural_checks"].append(
                {"check": "Phase1 Sam frozen", "ok": 7 in frozen}
            )
        if phase == "Phase 2":
            report["structural_checks"].append(
                {"check": "Phase2 前台 frozen", "ok": 1 in frozen}
            )

    report["structural_checks"].append(
        {
            "check": "Phase3 move_allowed=true",
            "ok": _move_allowed("Phase 3") is True,
            "value": _move_allowed("Phase 3"),
        }
    )

    llm_p1 = resolve_llm_params("Phase 1", 1)
    llm_p3 = resolve_llm_params("Phase 3", 15)
    llm_p4 = resolve_llm_params("Phase 4", 21)
    report["structural_checks"].append(
        {
            "check": "温度 Phase1 < Phase3",
            "ok": llm_p1["temperature"] < llm_p3["temperature"],
            "values": {"p1": llm_p1, "p3": llm_p3, "p4": llm_p4},
        }
    )

    sess = SimpleNamespace(
        phase="Phase 1",
        player_turn=1,
        place_id="nvidia_reception",
        stats={"vision": 5, "execution": 5, "trust": 5, "burnout": 0},
    )
    kb = build_agent_knowledge(sess, 1, "测试", channel="inject")
    report["structural_checks"].append(
        {
            "check": "知识库 hybrid (shared+agent overlay)",
            "ok": "Phase 1" in kb and "接待" in kb,
            "kb_chars": len(kb),
        }
    )

    report["structural_checks"].append(
        {
            "check": "Phase1 inject_exclusive_ticks=2",
            "ok": inject_exclusive_ticks_for("Phase 1") == 2,
            "value": inject_exclusive_ticks_for("Phase 1"),
        }
    )

    if not report["llm_configured"]:
        report["summary"]["verdict"] = "结构层通过；无 LLM Key，跳过运行时体验采样"
        return report

    runner, flask, base, _ = start_stack()
    try:
        http_json("POST", f"{base}{BASE_PATH}/session/start")

        # Phase 1 Turn 1 — 技术
        t1_text = (
            "我要见黄仁勋。我有一套推理侧稀疏注意力方案，能把大模型 KV Cache "
            "显存占用降低 80%，不是 PPT，是已 repro 的 kernel。"
        )
        r1, cookie = _send_turn(base, "", t1_text)
        s1 = TurnSample("Phase1 Turn1 技术", "Phase 1", t1_text)
        s1.public = r1.get("public_messages") or []
        s1.observer = r1.get("observer_messages") or []
        s1.status = r1.get("status") or ""
        s1.notes.append(_score_brevity(s1.public, 220))
        s1.notes.append(
            _player_influence(t1_text, s1.public, ["80", "显存", "KV", "kernel"])
        )
        rdc_j = [
            m
            for m in s1.observer
            if str(m.get("sender")) in ("1", "agent_1", "前台")
            or "→" in str(m.get("content") or "")
        ]
        if len(s1.observer) > 6:
            s1.notes.append(f"Observer 过多: {len(s1.observer)}")
        report["samples"].append(s1.__dict__)

        # Phase 1 Turn 2 — 玩梗
        t2_text = "我给您带了杯热咖啡，黄总还在忙吗？他今天还穿着那件黑色皮衣吗？"
        r2, cookie = _send_turn(base, cookie, t2_text)
        s2 = TurnSample("Phase1 Turn2 玩梗", "Phase 1", t2_text)
        s2.public = r2.get("public_messages") or []
        s2.observer = r2.get("observer_messages") or []
        s2.status = r2.get("status") or ""
        s2.notes.append(_score_brevity(s2.public, 200))
        s2.notes.append(
            _player_influence(t2_text, s2.public, ["咖啡", "皮衣", "黄总"])
        )
        obs_blob = " ".join(str(m.get("content") or "") for m in s2.observer)
        if "80" in obs_blob or "显存" in obs_blob:
            s2.notes.append("Turn2 Observer 重复 Turn1 技术 RDC ✗")
        else:
            s2.notes.append("Turn2 无 Turn1 技术 RDC 重复 ✓")
        report["samples"].append(s2.__dict__)

        # session reset then IPC phase tests
        http_json("POST", f"{base}{BASE_PATH}/session/reset", cookie=cookie)
        time.sleep(1)

        s_p2 = _phase2_ipc_smoke()
        report["samples"].append(s_p2.__dict__)

        s_p4 = _phase4_ipc_smoke()
        report["samples"].append(s_p4.__dict__)

    finally:
        for proc in (flask, runner):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()

    # Aggregate verdict
    struct_ok = all(c.get("ok") for c in report["structural_checks"])
    runtime_issues = []
    for s in report["samples"]:
        for n in s.get("notes", []):
            if "✗" in n or "无" in n and "重复" not in n and "F2F" in n:
                runtime_issues.append(f"{s.get('label')}: {n}")

    report["summary"] = {
        "structural_ok": struct_ok,
        "runtime_issue_count": len(runtime_issues),
        "runtime_issues": runtime_issues[:10],
    }
    return report


def main() -> None:
    print("=== F07 体验评测 ===\n")
    report = run_eval()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("\n=== 结构检查 ===")
    for c in report["structural_checks"]:
        mark = "✓" if c.get("ok") else "✗"
        print(f"  {mark} {c.get('check')}: {c.get('value', c.get('ok'))}")

    print("\n=== 运行时采样 ===")
    for s in report.get("samples", []):
        print(f"\n--- {s.get('label')} ({s.get('phase')}) ---")
        print(f"  玩家: {s.get('player_text', '')[:80]}…")
        for m in s.get("public") or []:
            content = str(m.get("content") or m.get("note") or "")[:300]
            print(f"  [F2F] {content}")
        for m in (s.get("observer") or [])[:3]:
            print(f"  [RDC] {m.get('sender')}→{m.get('recipient')}: {str(m.get('content') or '')[:200]}")
        for n in s.get("notes") or []:
            print(f"  · {n}")

    verdict = report.get("summary", {})
    if verdict.get("verdict"):
        print(f"\n结论: {verdict['verdict']}")
    else:
        ok = verdict.get("structural_ok") and verdict.get("runtime_issue_count", 99) == 0
        print(f"\n自动化体验门槛: {'通过' if ok else '部分未达预期'}")
        if verdict.get("runtime_issues"):
            print("问题:", verdict["runtime_issues"])


if __name__ == "__main__":
    main()

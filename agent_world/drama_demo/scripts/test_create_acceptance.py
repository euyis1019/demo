"""创建流程验收门禁（需求 K）：用户只给一段剧情 → 管理 agent 自动生成「完整可玩」整包。

真实 LLM 端到端（较慢、要 DMXAPI_KEY），故不并入快门禁 test_m0_acceptance.py，按需单跑：
    python3 scripts/test_create_acceptance.py

校验生成包：onboarding + acting_guide + 数据驱动属性(meta.stats) 齐；结构 validate() 通过；
bert（条件→反应）规则集非空且含结局 bert（剧情运行期主驱动）。
生成到隔离 story_id、验完即删，不污染 config/stories。
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

# 本脚本在进程内直接跑 generate_full，需自行加载 drama_demo/.env（DMXAPI_KEY 等）。
_ENV = Path(__file__).resolve().parents[1] / ".env"
if _ENV.is_file():
    for _line in _ENV.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())


def main() -> int:
    from agent_world.drama_demo.http.world_manager import WORLD_MANAGER
    from agent_world.drama_demo.shared.prompt_paths import story_dir
    from agent_world.drama_demo.shared.story_pack import load_story_pack

    premise = (
        "末日避难所第七层，资源即将耗尽，三个派系为最后一批净水暗中较劲；"
        "你是新当选、谁都不信任的临时管理员，必须在七天内分配资源、平息哗变、查出谁在囤积。"
    )
    print("→ 模拟用户建故事（只给一段剧情），管理 agent 异步生成整包…", flush=True)
    # 不传 acts：验证管理 agent(Designer) 按剧情自决任务/结局数（不再写死）。
    job_id = WORLD_MANAGER.create_story(premise=premise, player="临时管理员", with_assets=False)
    for _ in range(150):
        job = WORLD_MANAGER.jobs.get(job_id) or {}
        if job.get("status") in ("done", "error"):
            break
        time.sleep(2)
    job = WORLD_MANAGER.jobs.get(job_id) or {}
    sid = job.get("story_id")
    if job.get("status") != "done":
        print(f"  ✗ 生成失败：{job.get('error')}")
        return 1

    try:
        pack = load_story_pack(sid)
        meta = pack.meta or {}
        fails = []
        if not meta.get("onboarding"):
            fails.append("缺 onboarding")
        if not meta.get("acting_guide"):
            fails.append("缺 acting_guide")
        dims = (meta.get("stats") or {}).get("dimensions") or []
        if len(dims) < 2:
            fails.append(f"缺数据驱动属性维度 stats（{dims}）")
        struct = pack.validate()
        if struct:
            fails.append(f"结构 validate 不过：{struct[:3]}")
        # bert（条件→反应）是剧情运行期主驱动：必须生成、引用闭合、且至少有一个结局 bert。
        berts = pack.berts.berts
        if not berts:
            fails.append("缺 berts（剧情无任何「条件→反应」规则）")
        elif not pack.berts.ending_berts():
            fails.append("berts 里没有结局 bert（游戏无法收场）")
        if fails:
            print("  ✗ 生成包有缺口：")
            for f in fails:
                print("     -", f)
            return 1
        n_end = len(pack.berts.ending_berts())
        print(f"  ✓ 生成完整可玩包 story_id={sid}")
        print(f"     onboarding={bool(meta.get('onboarding'))} acting_guide={bool(meta.get('acting_guide'))}")
        print(f"     属性维度={[d.get('label') for d in dims]}")
        print(f"     bert 规则 {len(berts)} 条（含 {n_end} 个结局 bert）· 角色 {len(pack.agents.get('agents', []))} 个")
        print("\n创建流程验收通过 ✅（用户给一段剧情 → 完整可玩 bert 游戏）")
        return 0
    finally:
        if sid:
            shutil.rmtree(story_dir(sid), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

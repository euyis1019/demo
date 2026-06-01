"""StoryPack → 运行期 scenario dict 适配器（G0-Slice6，dev_logs/45 §6 / dev_logs/46 C-1）。

把一份 Story Pack 投影成 kernel.build_kernel / seed_world 消费的 scenario 形状，使运行期
播种代码**零改动**即可从 Story Pack 启动世界（开关式：仅当 DRAMA_STORY_PACK_SEED=1 时启用）。
这是「换 config 换世界」的运行期落点——seed/build_kernel 拿到的 scenario 来自 Story Pack 而非
外部 scenario。等价性由 test_story_pack_scenario_equiv 离线证明（投影 == load_scenario）。

纯数据转换（D3：shared 不依赖 features/runner）。consume 的 scenario 键（见 seed.py / kernel.py）：
  simulation_id · runner · clock · llm · places(place_id/capacity/attrs) · coverage ·
  capabilities[{agent_id,capability}] · groups · relations · agents(agent_id/name/location/soul/...)
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from agent_world.drama_demo.shared.story_pack.pack import StoryPack


def is_story_pack_seed_enabled() -> bool:
    """是否在 Runner 启动时从 Story Pack 播种世界（默认开（DRAMA_STORY_PACK_SEED 默认 1，设 0 才回退），旧 外部 scenario 路径不变）。

    开关式：`DRAMA_STORY_PACK_SEED=1` 才启用（dev_logs/46 C-1 / E-1 灰度）。播种等价已离线证明；
    切换前仍应跑完整 E2E 门禁。本助手放 shared/ 以便 L1 Runner 读取（不违反 D4）。
    """
    return os.environ.get("DRAMA_STORY_PACK_SEED", "1").strip() not in ("0", "false", "False", "no", "off")


def is_free_move_enabled() -> bool:
    """是否放开 agent 自主移动（request_move 真正生效）。默认开（DRAMA_STORY_PACK_SEED 默认 1，设 0 才回退）——旧版脚本搬人不变。

    开关式：`DRAMA_FREE_MOVE=1` 才放开（用户旋钮2）。放开时仍以 prompt 强引导「非必要不移动」，
    避免 agent 乱跑导致剧情卡死。本助手放 shared/ 以便 L1 Runner/dispatcher 读取（不违反 D4）。
    """
    return os.environ.get("DRAMA_FREE_MOVE", "").strip() in ("1", "true", "True", "yes", "on")

# scenario 里每个 agent 需要的键（其余如 role/faction/capabilities 不进 scenario.agents）。
_AGENT_KEYS = ("agent_id", "name", "location", "soul", "long_term_goal", "current_state", "short_term_goal")


def story_pack_to_scenario(pack: StoryPack) -> Dict[str, Any]:
    """把 Story Pack 投影成运行期 scenario dict。"""
    meta = pack.meta or {}

    scenario: Dict[str, Any] = {
        "simulation_id": meta.get("simulation_id"),
        "runner": dict(meta.get("runner") or {}),
        "clock": dict(meta.get("clock") or {}),
        "llm": dict(meta.get("llm") or {}),
        "places": [],
        "coverage": list(pack.places.get("coverage") or []),
        "capabilities": [],
        "groups": list(pack.groups.get("groups") or []),
        "relations": list(pack.relations.get("relations") or []),
        "agents": [],
    }

    # places：保留 seed/kernel 关心的键（place_id/capacity/attrs，可选 place_type/parent_id）。
    for p in pack.places.get("places") or []:
        place: Dict[str, Any] = {"place_id": p["place_id"]}
        for k in ("place_type", "parent_id", "capacity", "attrs"):
            if k in p:
                place[k] = p[k]
        scenario["places"].append(place)

    # agents + capabilities 展开（agents[].capabilities → 顶层 [{agent_id,capability}] 行）。
    caps: List[Dict[str, Any]] = []
    for a in pack.agents.get("agents") or []:
        agent = {k: a[k] for k in _AGENT_KEYS if k in a}
        scenario["agents"].append(agent)
        aid = int(a["agent_id"])
        for cap in a.get("capabilities") or []:
            caps.append({"agent_id": aid, "capability": str(cap)})
    scenario["capabilities"] = caps

    return scenario

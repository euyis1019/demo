"""《焐心小镇》玩法层纯逻辑单测（不依赖 LLM / 不起世界）。

覆盖：送心意/搭把手翻译（gift_help）、时段映射（day_phase）、终局软推力（WorldDirector）。
daily_digest 等需起世界的路径由 WS 端到端验收覆盖，这里只锁定可纯函数测试的确定性逻辑。
"""

from __future__ import annotations

from cyber_town.backend.agents.bonds import bond_from_score
from cyber_town.backend.config import classify_activity, day_phase
from cyber_town.backend.directors.world_director import WorldDirector
from cyber_town.backend.interactions import GiftHelp
from cyber_town.backend.prompts.directors import FINALE_FACT


# ---- 送心意 / 搭把手 ---------------------------------------------------------

def test_gifthelp_catalog_covers_three_npcs():
    cat = GiftHelp().catalog()
    assert set(cat.keys()) == {"1", "2", "3"}
    for npc in cat.values():
        assert npc["gifts"] and npc["helps"]
        for item in npc["gifts"] + npc["helps"]:
            assert item["id"] and item["label"]


def test_gifthelp_translate_valid_to_speak_to_local():
    gh = GiftHelp()
    cmd = gh.translate("give_gift", {"target": 3, "item": "hoe"})
    assert cmd["action"] == "speak_to_local"
    assert "锄头" in cmd["kwargs"]["content"]
    # 搭把手走 helps 表
    cmd2 = gh.translate("lend_a_hand", {"target": 2, "item": "prep"})
    assert cmd2["action"] == "speak_to_local" and cmd2["kwargs"]["content"]


def test_gifthelp_companions_spend_time():
    gh = GiftHelp()
    # B2：陪伴类目存在且 spend_time 可翻译
    assert all("companions" in v and v["companions"] for v in gh.catalog().values())
    cmd = gh.translate("spend_time", {"target": 1, "item": "drink"})
    assert cmd["action"] == "speak_to_local" and "钱叔" in cmd["kwargs"]["content"]


def test_gifthelp_translate_invalid_returns_none():
    gh = GiftHelp()
    assert gh.translate("give_gift", {"target": 3, "item": "nope"}) is None   # 未知 item
    assert gh.translate("give_gift", {"target": 99, "item": "hoe"}) is None    # 未知对象
    assert gh.translate("lend_a_hand", {"target": 3, "item": "hoe"}) is None   # item 串了表（hoe 是礼物非帮忙）
    assert gh.translate("speak_to_local", {"target": 3, "item": "hoe"}) is None  # 非交互动作
    assert gh.translate("give_gift", {"item": "hoe"}) is None                  # 缺 target


# ---- 时段映射 ---------------------------------------------------------------

def test_day_phase_boundaries():
    assert day_phase("05:00") == "清晨"
    assert day_phase("10:59") == "清晨"
    assert day_phase("11:00") == "晌午"
    assert day_phase("16:00") == "傍晚"
    assert day_phase("19:59") == "傍晚"
    assert day_phase("20:00") == "夜里"
    assert day_phase("03:00") == "夜里"


def test_day_phase_degrades_gracefully():
    assert day_phase("") == ""
    assert day_phase("bad") == ""


# ---- 终局软推力 -------------------------------------------------------------

def test_finale_fires_once_when_all_max():
    wd = WorldDirector(client=None, model="x")
    wd.finale_checker = lambda: False
    wd.maybe_decide(None, 5)
    assert wd.current_event(5) is None             # 条件不满足，不投放

    wd.finale_checker = lambda: True
    wd.maybe_decide(None, 5)
    assert wd.current_event(5) == FINALE_FACT        # 三人皆挚友 → 投放接风事实

    wd._event = None                                 # 模拟事件被消费/清空
    wd.maybe_decide(None, 6)
    assert wd.current_event(6) is None               # 只投一次，不重复


def test_finale_silent_when_checker_raises():
    wd = WorldDirector(client=None, model="x")
    wd.finale_checker = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    wd.maybe_decide(None, 5)                          # 判定异常被吞，不崩
    assert wd.current_event(5) is None


# ---- 活动动画分类（B1）------------------------------------------------------

def test_classify_activity():
    assert classify_activity("在田里锄地") == "work"
    assert classify_activity("蹲田埂上歇脚") == "sit"
    assert classify_activity("躺树荫里午睡") == "lie"
    assert classify_activity("举杯乐呵") == "cheer"
    assert classify_activity("站着发呆") == "idle"
    assert classify_activity("") == "idle"


# ---- 羁绊由好感派生（B4 系统派生版）----------------------------------------

def test_bond_from_score():
    assert bond_from_score(80) == "好友"      # 高好感 → 好友
    assert bond_from_score(75) == "好友"
    assert bond_from_score(60) is None        # 亲密但未到好友门槛
    assert bond_from_score(30) is None
    assert bond_from_score(8) == "心结"        # 跌到很低 → 心结
    assert bond_from_score(0) == "心结"
    assert bond_from_score(None) is None

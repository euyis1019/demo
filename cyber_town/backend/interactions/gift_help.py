"""GiftHelp —— 玩家「送心意 / 搭把手」交互薄层（M-game1/M-game5）。

设计（焐心小镇支柱 3，评委验证的零风险路径）：
* 玩家在前端选「送某人某份心意 / 帮某人某件忙」→ 上行 ``give_gift`` /
  ``lend_a_hand`` 命令；
* 本薄层把它**翻译成一句中文叙述的 F2F ``speak_to_local``**（"（递上一把
  崭新的锄头）大山哥，这把你拿着使。"），走**现成玩家命令通道**入队——
  不新增引擎动词、不改 dispatcher、不动玩家白名单（speak_to_local 已在白名单）；
* **绝不后端代加好感**：NPC 像对任何当面话一样自主领情、自主 ``adjust_affinity``。

红线对齐（守红线 4：前后端引擎三方对齐）：
* 礼物/帮忙清单**服务端唯一定义**在 ``_CATALOG``；
* 经 hello 帧的 ``interactions`` 字段下发前端做枚举（前端只渲染、不杜撰）；
* 因翻译成 F2F，必须当面（同地点）才送得出去——前端按 co-location 门控按钮。

类型：``give_gift`` 取 ``gifts``，``lend_a_hand`` 取 ``helps``；
命令 kwargs = ``{target: npc_id, item: item_id}``。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# 礼物/帮忙叙述句以「玩家(农场主)当面做+说」的口吻写——会经 F2F 广播，
# 在场 NPC 看到「农场主 说：<content>」，自主决定如何领情。
# 做成**对象专属、有意义**的（评委警告：通用礼物会塌成刷分），让 LLM 有
# 可差异化领情的素材。结构：{npc_id: {"gifts"|"helps": [(item_id, label, 叙述句)]}}
_CATALOG: Dict[int, Dict[str, List[Tuple[str, str, str]]]] = {
    1: {  # 老钱 —— 杂货铺老板，精明热心
        "gifts": [
            ("eggs", "送一篮自家鸡蛋",
             "（拎来一篮还带着温气的土鸡蛋）钱叔，自家鸡下的，给你留了一篮。"),
            ("trinket", "送个稀罕小玩意",
             "（掏出个外头带回来的小物件）钱叔，瞧见这个就想起你，拿着玩儿。"),
        ],
        "helps": [
            ("shop", "帮看店招呼客",
             "（往柜台后一站）钱叔，你歇会儿喝口茶，这阵我帮你招呼着。"),
            ("stock", "帮搬货上架",
             "（挽起袖子搬起货箱）钱叔，这些重货我来，给你码上架。"),
        ],
    },
    2: {  # 阿香 —— 酒馆老板娘，爽利八卦
        "gifts": [
            ("gossip", "带一桩镇上趣闻",
             "（神秘兮兮凑过去）香姐，跟你说个新鲜事儿，保准你爱听。"),
            ("spice", "送一包好卤料",
             "（递上一包香料）香姐，托人带的卤料，配你那手艺正好。"),
        ],
        "helps": [
            ("prep", "搭把手备料",
             "（系上围裙）香姐，晚市的料我帮你备，你指挥。"),
            ("serve", "帮招呼客人",
             "（端起托盘）香姐，忙不过来我来跑堂，你尽管张罗。"),
        ],
    },
    3: {  # 大山 —— 庄稼汉，实在
        "gifts": [
            ("hoe", "送一把新锄头",
             "（递上一把崭新的锄头）大山哥，看你那把都卷刃了，这把你拿着使。"),
            ("veggies", "送自家种的菜",
             "（拎来一篮水灵灵的青菜）大山哥，自家地里现摘的，给你尝尝鲜。"),
        ],
        "helps": [
            ("harvest", "帮收一垄庄稼",
             "（卷起袖子下到田里）大山哥，我来搭把手，这垄我帮你收了。"),
            ("water", "帮挑水浇地",
             "（挑起水桶往田里走）大山哥，歇着，这水我来挑，地我帮你浇上。"),
        ],
    },
}

_ACTION_TO_KIND = {"give_gift": "gifts", "lend_a_hand": "helps"}


class GiftHelp:
    """送心意/搭把手目录 + 命令翻译（无状态，按 _CATALOG 查表）。"""

    def catalog(self) -> Dict[str, Dict[str, List[Dict[str, str]]]]:
        """供 hello 下发前端：{npc_id: {gifts:[{id,label}], helps:[{id,label}]}}。"""
        return {
            str(npc): {
                kind: [{"id": iid, "label": label} for iid, label, _ in items]
                for kind, items in kinds.items()
            }
            for npc, kinds in _CATALOG.items()
        }

    def translate(self, action: str, kwargs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """``give_gift``/``lend_a_hand`` → ``speak_to_local`` 命令；非法返回 None。"""
        kind = _ACTION_TO_KIND.get(action)
        if kind is None:
            return None
        try:
            target = int(kwargs.get("target"))
            item = str(kwargs.get("item", ""))
        except (TypeError, ValueError):
            return None
        for iid, _, narrative in _CATALOG.get(target, {}).get(kind, []):
            if iid == item:
                log.info("玩家%s：target=%s item=%s → speak_to_local", action, target, item)
                return {"action": "speak_to_local", "kwargs": {"content": narrative}}
        log.warning("未知的%s：target=%s item=%s", action, target, kwargs.get("item"))
        return None

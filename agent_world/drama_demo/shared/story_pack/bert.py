"""Bert（条件→反应）数据模型 —— 取代旧的「分幕/节点/任务链」剧情结构。

一个 **bert** 是一条「玩家做某事 → 某个 NPC 产生某个反应」的剧情规则（无 phase、无任务）：
  trigger（玩家做/说了什么，自然语言）→ target（哪个 NPC）→ reaction（他触发后要演的反应）。
多条 bert 经 requires/arms 串成**反应链**。`ending` 非空的 bert 是**结局 bert**：触发即收场。

运行期由「Bert 导演」(LLM) 读对话判 trigger 是否命中，命中就把 reaction 注入 target 的下一拍 prompt。
纯数据/算法，不依赖 features（D3）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent_world.drama_demo.shared.story_pack.errors import StoryPackError

ENDING_KINDS = ("good", "neutral", "bad")


def _require(mapping: Dict[str, Any], key: str, ctx: str) -> Any:
    if key not in mapping or mapping[key] in (None, ""):
        raise StoryPackError(f"{ctx} 缺少必填字段 '{key}'：{mapping!r}")
    return mapping[key]


def _as_int(value: Any, default: int = 0) -> int:
    """容错把 target(agent_id) 转成 int：LLM 偶尔给 "3" 这样的字符串数字。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Bert:
    """一条「条件→反应」规则。

    target: 反应的 agent_id；结局 bert 可为 0/省略（结局不一定有特定 NPC 反应）。
    ending: 非空 = 结局 bert，{kind: good|neutral|bad, summary}；触发即游戏收场。
    arms: 本 bert 触发后「上膛」哪些后续 bert（反应链）。
    requires: 需先触发过哪些 bert，本 bert 才上膛（反应链前置）；空 = 开局即上膛。
    """

    id: str
    trigger: str
    reaction: str = ""
    hint: str = ""  # 玩家向「线索」：一句勾而不破的下一步提示（指向本条 trigger，不剧透后果）。删幕后给玩家随进度更新的目标感。
    target: int = 0
    place: str = ""
    once: bool = True
    arms: List[str] = field(default_factory=list)
    requires: List[str] = field(default_factory=list)
    ending: Optional[Dict[str, Any]] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_ending(self) -> bool:
        return bool(self.ending)

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "Bert":
        bid = str(_require(data, "id", "bert"))
        _require(data, "trigger", f"bert '{bid}'")
        ending = data.get("ending") or None
        if ending is not None and not isinstance(ending, dict):
            raise StoryPackError(f"bert '{bid}' 的 ending 必须是 mapping")
        return cls(
            id=bid,
            trigger=str(data.get("trigger") or ""),
            reaction=str(data.get("reaction") or ""),
            hint=str(data.get("hint") or ""),
            target=_as_int(data.get("target"), 0),
            place=str(data.get("place", "") or ""),
            once=bool(data.get("once", True)),
            arms=[str(x) for x in (data.get("arms") or [])],
            requires=[str(x) for x in (data.get("requires") or [])],
            ending=dict(ending) if ending else None,
            raw=dict(data),
        )


@dataclass
class BertSet:
    """一个故事的全部 bert（id → Bert）。"""

    berts: Dict[str, Bert] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "BertSet":
        if not isinstance(data, dict):
            raise StoryPackError("berts 顶层必须是 mapping")
        out: Dict[str, Bert] = {}
        for raw in data.get("berts") or []:
            b = Bert.from_mapping(raw)
            if b.id in out:
                raise StoryPackError(f"重复 bert id：{b.id}")
            out[b.id] = b
        return cls(berts=out)

    def initially_armed(self) -> List[str]:
        """开局就「上膛」的 bert（requires 为空，且没有别的 bert 用 arms 显式上膛它）。"""
        return self.armed_ids(set())

    def _arming_map(self) -> Dict[str, set]:
        """bid → 「哪些 bert 用 arms 显式上膛它」。"""
        arming: Dict[str, set] = {}
        for bid, b in self.berts.items():
            for a in b.arms:
                arming.setdefault(a, set()).add(bid)
        return arming

    def armed_ids(self, fired: set) -> List[str]:
        """给定已触发集合 fired，算出当前「上膛」(可被判定触发) 的 bert id。

        一条 bert 上膛当且仅当：
          - 不是「once 且已触发」（已用掉的一次性 bert 退出）；
          - 它的全部 requires 都已在 fired 中（前置链满足）；
          - 没有别的 bert 用 arms 指向它，或至少有一个这样的 bert 已触发（被显式上膛）。
        requires 与 arms 是同一条反应链边的两种写法，这里统一兜住。
        """
        arming = self._arming_map()
        out: List[str] = []
        for bid, b in self.berts.items():
            if b.once and bid in fired:
                continue
            if not set(b.requires) <= fired:
                continue
            armers = arming.get(bid)
            if armers and not (armers & fired):
                continue  # 被别的 bert 显式上膛，但那条还没触发
            out.append(bid)
        return out

    def ending_berts(self) -> List[str]:
        return [bid for bid, b in self.berts.items() if b.is_ending]

    def current_hints(self, fired: set) -> List[str]:
        """当前可循的「线索」：此刻已上膛、尚未触发、非结局、且配了 hint 的 bert 的玩家向提示。

        随玩家触发 bert（fired 增长）→ 上膛集合推进 → 线索自动换成下一批，给玩家「按线索推进」的指引。
        去重保序：同一句 hint 只出一次。"""
        out: List[str] = []
        seen: set = set()
        for bid in self.armed_ids(set(fired)):
            b = self.berts[bid]
            if b.is_ending or bid in fired or not b.hint:
                continue
            if b.hint not in seen:
                seen.add(b.hint)
                out.append(b.hint)
        return out

    # ---------- validate ----------
    def validate(
        self,
        *,
        agent_ids: Optional[set] = None,
        place_ids: Optional[set] = None,
        strict: bool = False,
    ) -> List[str]:
        """结构 + 引用闭合校验。返回违例列表（空=通过）。

        strict=True 额外加「开局可玩面」软门禁 [B9]/[B10]——只在**生成期**用来逼管理 agent 产出
        玩家上手就能推进的开局；运行期加载(load_and_validate)走默认 strict=False，**不因可玩面问题拒载
        已有故事**（旧故事照常能玩，可玩面问题留待下次重新生成时由生成门禁兜）。
        """
        issues: List[str] = []
        if not self.berts:
            issues.append("[B0] 至少要有 1 条 bert")
        ids = set(self.berts)
        has_ending = False
        for bid, b in self.berts.items():
            # 引用闭合：arms/requires 必须是已知 bert
            for ref in (*b.arms, *b.requires):
                if ref not in ids:
                    issues.append(f"[B1] bert '{bid}' 引用了不存在的 bert：{ref}")
            # target ∈ agents（结局 bert 可无 target）
            if agent_ids is not None and not b.is_ending and b.target and int(b.target) not in agent_ids:
                issues.append(f"[B2] bert '{bid}' 的 target 不是已知 agent：{b.target}")
            if place_ids is not None and b.place and b.place not in place_ids:
                issues.append(f"[B3] bert '{bid}' 的 place 不是已知地点：{b.place}")
            # 非结局 bert 须有 reaction + target
            if not b.is_ending:
                if not str(b.reaction).strip():
                    issues.append(f"[B4] bert '{bid}' 缺 reaction（NPC 触发后要演什么）")
                if not b.target:
                    issues.append(f"[B5] bert '{bid}' 缺 target（哪个 NPC 反应）")
            else:
                has_ending = True
                kind = str((b.ending or {}).get("kind", ""))
                if kind not in ENDING_KINDS:
                    issues.append(f"[B6] 结局 bert '{bid}' 的 kind 非法（须 good/neutral/bad）：{kind}")
        if not has_ending:
            issues.append("[B7] 至少要有 1 条结局 bert（ending 非空），否则游戏无法收场")
        # 可达性：每条 bert 都应「最终能上膛」——与运行期 armed_ids 同义（requires 全可达 + 若被 arms 指向则其上膛者可达），
        # 经不动点扩张。注意：requires 与 arms 都算前置边（二者是反应链同一条边的两种写法），不能只跟 arms。
        reachable = set(self.initially_armed())
        arming = self._arming_map()
        changed = True
        while changed:
            changed = False
            for bid, b in self.berts.items():
                if bid in reachable:
                    continue
                if not set(b.requires) <= reachable:
                    continue
                armers = arming.get(bid)
                if armers and not (armers & reachable):
                    continue
                reachable.add(bid)
                changed = True
        orphans = sorted(ids - reachable)
        if orphans:
            issues.append(f"[B8] 存在「永不上膛」的孤儿 bert（无前置链可达）：{orphans}")
        if strict:
            # [B9] 开局可玩面：开局必须有可触发的非结局 bert，否则玩家一上来无从下手（怎么说都没反应）。
            opening = set(self.initially_armed())
            open_play = [bid for bid in opening if not self.berts[bid].is_ending]
            if not open_play:
                issues.append(
                    "[B9] 开局没有任何可触发的非结局 bert（玩家一上来无从推进）：开局上膛 ＝ requires 为空"
                    "且没被任何 bert 用 arms 指向；请至少留 1 条（建议≥2、覆盖多个在场 NPC）开局入口"
                )
            # [B10] requires/arms 自相矛盾：requires 为空（本意开局上膛）却又被别的 bert 用 arms 指向
            # （实为被那条上膛、开局其实锁死）。反应链设计错误——要么别被 arms 指向、要么给它非空 requires。
            contradicted = sorted(
                bid for bid, b in self.berts.items() if not b.requires and arming.get(bid)
            )
            if contradicted:
                issues.append(
                    f"[B10] 这些 bert 的 requires 为空却又被别的 bert 用 arms 指向，自相矛盾（开局其实锁死）："
                    f"{contradicted}；要开局可触发就别被 arms 指向，要串作后续就给它非空 requires"
                )
        return issues

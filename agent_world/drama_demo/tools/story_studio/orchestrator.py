"""story_studio 编排器骨架（dev_logs/45 §1.3 / §6 G1）。

职责：assemble sections → 落盘 → validate 闸门（不含 LLM 业务；agent 调用在 G2 接入）。
本切片（G1）提供「纯落盘 + 校验」骨架：给一组 sections（手写或由管理 agent 产出），
组装成 Story Pack 写盘并跑加载期 validate。Plan→Review→Revise 回路与真实 agent 流水线在 G2+。

落点固定 config/stories/<id>/；写盘走 writer.assert_safe_target 红线。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent_world.drama_demo.shared.prompt_paths import story_dir
from agent_world.drama_demo.shared.story_pack import load_story_pack
from agent_world.drama_demo.tools.story_studio.writer import write_story_pack


@dataclass
class CompileResult:
    story_id: str
    target_dir: Path
    issues: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def brief_to_meta(brief: Dict[str, Any], story_id: str) -> Dict[str, Any]:
    """从 brief 投影一份最小 meta（标题/玩家）；完整 clock/llm 由 _full_meta 补。"""
    import re as _re

    player = brief.get("player") or {}
    # 标题：优先用户给的 title；否则取 premise 的第一句（按句读/逗号断，不在词中硬截到 40 字病句）。
    premise = str(brief.get("premise") or "").strip()
    first_clause = _re.split(r"[。．.！!？?，,；;\n]", premise, 1)[0].strip() if premise else ""
    raw_title = str(brief.get("title") or "").strip() or first_clause
    # 容错：用户常把整段带标签的模板（如「标题：xxx\n一段剧情：…」）贴进来——
    # 只取第一行、剥掉「标题/剧情标题/title：」之类前缀标签，避免标题被污染成「标题：xxx\n…」。
    raw_title = raw_title.splitlines()[0] if raw_title else ""
    raw_title = _re.sub(r"^\s*(剧情标题|故事标题|标题|title)\s*[：:]\s*", "", raw_title, flags=_re.I).strip()
    title = raw_title[:60] or story_id
    return {
        "schema_version": 1,
        "simulation_id": story_id,
        "title": title,
        "player": {
            "agent_id": 0,
            "name": player.get("identity", "玩家"),
            "role": player.get("role", "player"),
        },
    }


def _sanitize_player_agent(agents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """机制级保证：玩家(agent 0)不带人设字段——否则 knowledge.py 会把玩家当 NPC 注入 soul/inner，污染表演。
    不靠 Casting 提示词自觉留空。"""
    out: List[Dict[str, Any]] = []
    for a in agents or []:
        if int(a.get("agent_id", -1)) == 0:
            a = {**a, "soul": "", "inner": "", "speech_style": "", "speech_samples": [],
                 "long_term_goal": "", "current_state": "", "opening_line": "", "capabilities": []}
        out.append(a)
    return out


def assemble_sections(
    meta: Dict[str, Any], casting: Dict[str, Any], bert_design: Dict[str, Any],
) -> Dict[str, Any]:
    """合并 meta + Casting(世界原语) + Bert 设计师(条件→反应规则集) → 完整 sections（无 story_graph）。"""
    return {
        "meta": meta,
        "places": {"places": casting.get("places", []), "coverage": casting.get("coverage", [])},
        "agents": {"agents": _sanitize_player_agent(casting.get("agents", []))},
        "relations": {"relations": casting.get("relations", [])},
        "relation_types": {"relation_types": casting.get("relation_types", [])},
        "groups": {"groups": casting.get("groups", [])},
        "berts": {"berts": bert_design.get("berts", [])},
    }


def _full_meta(brief: Dict[str, Any], story_id: str, casting: Dict[str, Any]) -> Dict[str, Any]:
    meta = brief_to_meta(brief, story_id)
    player_loc = next(
        (a.get("location") for a in casting.get("agents", []) if int(a.get("agent_id", -1)) == 0), None
    )
    if player_loc:
        meta["player"]["start_place"] = player_loc
    meta["clock"] = {"start_time": "09:00", "minutes_per_tick": 2}
    meta["runner"] = {"parallel_agent_decisions": True}
    meta["llm"] = brief.get("llm") or {
        "base_url": "https://api.deepseek.com", "api_key_env": "DMXAPI_KEY",
        "model": "deepseek-chat", "temperature": 0.7, "max_tokens": 500,
    }
    return meta


def assemble_full_sections(
    brief: Dict[str, Any], story_id: str, casting: Dict[str, Any], bert_design: Dict[str, Any],
) -> Dict[str, Any]:
    """从 brief 出发组装完整 sections（生成路径）。"""
    return assemble_sections(_full_meta(brief, story_id, casting), casting, bert_design)


def generate_full(
    brief: Dict[str, Any], *, story_id: str, client: Any,
    target_dir: Optional[Path] = None, max_rounds: int = 3,
    max_llm_calls: Optional[int] = None, trace: Any = None,
    critic_rounds: int = 2, critic_threshold: int = 3,
    on_progress: Optional[Callable[[str], None]] = None,
) -> CompileResult:
    """完整流水线 Casting→Bert 设计师→assemble→validate(X+B)→失败回灌重生成，
    结构合法后再过 **Critic 质量门**（按叙事 rubric 评分，低分则把意见回灌定向重写 Casting/Bert）。
    剧情结构由 bert（条件→反应）承载，已无 Designer/Writer/story_graph（见 dev_logs/48）。

    产出**完整可运行**且经质量评审的 Story Pack。client 注入，离线可测。
    可选 max_llm_calls 成本护栏 + trace 生成决策链记录。critic_rounds=0 可关闭质量门（如离线 fake client）。
    on_progress(msg)：每完成一个阶段回调一句中文进度（终端日志 + 前端进度共用），不传则静默。
    """
    from agent_world.drama_demo.tools.story_studio.agents.bert_designer import BertDesigner
    from agent_world.drama_demo.tools.story_studio.agents.casting import Casting
    from agent_world.drama_demo.tools.story_studio.agents.critic import Critic
    from agent_world.drama_demo.tools.story_studio.base_agent import StoryStudioError
    from agent_world.drama_demo.tools.story_studio.metering import metering_client

    _p = on_progress or (lambda *_a: None)
    client = metering_client(client, max_calls=max_llm_calls, trace=trace)
    casting, bert_designer = Casting(client), BertDesigner(client)
    feedback = ""
    last_issues: List[str] = []
    c = b = None
    sections: Dict[str, Any] = {}
    result: Optional[CompileResult] = None

    # ① 结构回路：产出结构/引用合法的整包（选角 + bert「条件→反应」反应链）。
    #    bert 的引用闭合/反应链可达/至少一个结局由 pack.validate（B 系列）兜，不达标连同其它违例回灌重生成。
    structural_ok = False
    for _round in range(max_rounds):
        _rd = f"（第 {_round + 1} 轮）" if _round else ""
        _p(f"① 选角与世界 Casting{_rd}…")
        c = casting.run(brief, feedback=feedback)
        _p(f"② 设计 bert 反应链（条件→反应 + 结局）{_rd}…（{len(c.get('agents') or [])} 个角色）")
        b = bert_designer.run(brief, c, feedback=feedback)
        _p("③ 组装并校验整包…")
        sections = assemble_full_sections(brief, story_id, c, b)
        result = compile_pack(sections, story_id=story_id, target_dir=target_dir)
        if result.ok:
            structural_ok = True
            break
        last_issues = list(result.issues)
        feedback = "整包未过验收：\n" + "\n".join(last_issues) + "\n请修正后重新输出完整 JSON。"
    if not structural_ok:
        raise StoryStudioError(f"generate_full '{story_id}' 失败：{max_rounds} 轮仍未过验收：{last_issues}")

    # ② 质量回路：Critic 按 rubric 评分，低分项把意见回灌定向重写 Casting/Writer（骨架 d 固定不动）。
    #    任一重写若破坏结构 → 回滚到上一版已合法的包并停止；评审本身报错也不阻断（保留已合法包）。
    if critic_rounds > 0:
        critic = Critic(client)
        last_good = sections
        for _q in range(critic_rounds):
            _p(f"④ 质量评审第 {_q + 1} 轮 Critic…")
            try:
                review = critic.review(brief, c, b)
            except Exception:  # noqa: BLE001 — 评审失败不阻断：保留已结构合法的包
                break
            import json as _json
            scores = review.get("scores") or {}
            low = [k for k, v in scores.items() if isinstance(v, int) and v < critic_threshold]
            cfb = (review.get("casting_feedback") or "").strip()
            bfb = (review.get("bert_feedback") or "").strip()
            if not low or (not cfb and not bfb):
                break  # 质量达标 / 评审无可执行意见 → 收工
            # 只在「角色维度」低时重写 casting、「bert 维度」低时重写 bert——避免无谓连带重写（省 LLM、防把高分项改坏）。
            cast_low = any(k in ("character_depth", "voice_distinct") for k in low)
            if cfb and cast_low:
                # 增量修订：带上一版角色卡，保 agent_id/name/数量不变只改被点字段——否则从头重生成会让 id 漂移、
                # bert 里 target/requires/arms 的引用整体错位（一致性只靠 validate 回滚=丢弃整轮改进，等于白评）。
                c = casting.run(brief, feedback=(
                    "【在下面这版角色卡基础上按评审意见修订：保持每个 agent_id、name 和角色数量不变，"
                    "只改被点到的字段，仍输出完整 JSON】\n上一版角色卡：\n"
                    + _json.dumps(c.get("agents", []), ensure_ascii=False) + "\n\n评审意见：\n" + cfb))
            if bfb or cast_low:  # bert 维度低、或角色卡刚被改 → bert 都要随之复核以保持一致
                b = bert_designer.run(brief, c, feedback=(
                    "【角色卡可能已按评审修订（agent_id/名字未变）。据此复核改进 bert：保持 bert id 与 requires/arms 引用自洽，"
                    "让 trigger 更清晰、reaction 更贴人设口吻、反应链更连贯，仍输出完整 JSON】\n评审意见：\n"
                    + (bfb or "（无 bert 专项意见，按最新角色设定微调 reaction 口吻即可）")))
            revised = assemble_full_sections(brief, story_id, c, b)
            r2 = compile_pack(revised, story_id=story_id, target_dir=target_dir)
            if r2.ok:
                result, last_good = r2, revised
            else:
                compile_pack(last_good, story_id=story_id, target_dir=target_dir)  # 回滚已合法包
                break

    # 设计期管理 agent 附加产物：仅在完整生成（critic_rounds>0，真实 client 的生产路径）时跑；
    # 离线 fake-client 测试关 critic 也顺带跳过。任一步失败都不阻断已结构合法的包。
    if critic_rounds > 0:
        # 新手引导：管理 agent 生成「故事背景 + 此刻可做的行为」，写进 meta.onboarding。
        try:
            from agent_world.drama_demo.tools.story_studio.onboarding import generate_onboarding

            _p("⑤ 生成新手引导…")
            # 把「开局即可触发的玩家动作(trigger)」喂给引导生成，让 tips 指向真能推进剧情的下一步，
            # 不再建议触发不了的死动作——这是"玩家不知道怎么推进"的主因之一。
            opening_triggers = None
            try:
                from agent_world.drama_demo.shared.story_pack.bert import BertSet

                _bs = BertSet.from_mapping({"berts": (b or {}).get("berts", [])})
                _armed = set(_bs.initially_armed())
                opening_triggers = [
                    bt.trigger
                    for bid, bt in _bs.berts.items()
                    if bid in _armed and not bt.is_ending and bt.trigger
                ] or None
            except Exception:  # noqa: BLE001
                opening_triggers = None
            onb = generate_onboarding(brief, c, client, opening_triggers=opening_triggers)
            _patch_meta(story_id, target_dir, "onboarding", onb)
        except Exception:  # noqa: BLE001
            pass

        # 表演须知：管理 agent 按本故事基调生成「该怎么演」的导演手册，写进 meta.acting_guide。
        # 运行期 knowledge.py 只注入这段、不再内嵌表演规则（dev_logs/43 管理 vs 演员）。
        try:
            from agent_world.drama_demo.tools.story_studio.acting_guide import generate_acting_guide

            _p("⑥ 生成表演须知…")
            guide = generate_acting_guide(brief, c, client)
            if guide:
                _patch_meta(story_id, target_dir, "acting_guide", guide)
        except Exception:  # noqa: BLE001
            pass

        # 属性面板：管理 agent 按故事生成可量化维度集 + 打分裁判，写进 meta.stats。
        # 运行期 f04 scoring 据此泛化打分、前端据此渲染 HUD，引擎不写死任何故事专属维度。
        try:
            from agent_world.drama_demo.tools.story_studio.stats_design import generate_stats_design

            _p("⑦ 生成属性面板…")
            stats = generate_stats_design(brief, c, client)
            if stats.get("dimensions"):
                _patch_meta(story_id, target_dir, "stats", stats)
        except Exception:  # noqa: BLE001
            pass

        # 世界规则：管理 agent 按故事基调决定运行期开关（目前：NPC 是否自主走动），写进 meta.world。
        # 运行期 scenario_adapter.is_free_move_enabled 据此放行/抑制 agent 的 request_move，引擎不写死。
        try:
            from agent_world.drama_demo.tools.story_studio.world_rules import generate_world_rules

            _p("⑧ 设定世界规则（NPC 是否自主走动）…")
            world = generate_world_rules(brief, c, client)
            _patch_meta(story_id, target_dir, "world", world)
        except Exception:  # noqa: BLE001
            pass

    return result


def _patch_meta(story_id: str, target_dir: Optional[Path], key: str, value: Any) -> None:
    """把管理 agent 的附加产物写进已落盘的 meta.yaml（过安全红线；均为 meta 的可选附加字段）。"""
    import yaml

    from agent_world.drama_demo.tools.story_studio.safety import assert_safe_target

    target = assert_safe_target(Path(target_dir) if target_dir is not None else story_dir(story_id))
    meta_path = target / "meta.yaml"
    if not meta_path.is_file():
        return
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    meta[key] = value
    meta_path.write_text(
        yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8")


def compile_pack(
    sections: Dict[str, Any],
    *,
    story_id: str,
    target_dir: Optional[Path] = None,
) -> CompileResult:
    """组装 sections → 写 Story Pack → 跑 validate。返回违例（空=通过）。

    target_dir 默认 config/stories/<id>/；测试可传临时目录。写盘前过安全红线。
    """
    target = Path(target_dir) if target_dir is not None else story_dir(story_id)
    write_story_pack(sections, target)
    # 仅当写到生产落点时用标准 loader 校验；否则在该目录就地校验。
    pack = load_story_pack(story_id) if target == story_dir(story_id) else _load_pack_from_dir(story_id, target)
    return CompileResult(story_id=story_id, target_dir=target, issues=pack.validate())


def _load_pack_from_dir(story_id: str, directory: Path):
    """从任意目录加载 StoryPack（测试用；生产走 story_dir）。"""
    import yaml

    from agent_world.drama_demo.shared.story_pack.bert import BertSet
    from agent_world.drama_demo.shared.story_pack.graph import StoryGraph
    from agent_world.drama_demo.shared.story_pack.pack import StoryPack, _OPTIONAL

    def _load(name: str) -> Dict[str, Any]:
        path = directory / f"{name}.yaml"
        if not path.is_file():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    meta = _load("meta")
    graph = StoryGraph.from_mapping(_load("story_graph"))
    berts = BertSet.from_mapping(_load("berts")) if (directory / "berts.yaml").is_file() else BertSet()
    pack = StoryPack(story_id=story_id, meta=meta, graph=graph, berts=berts)
    for name in _OPTIONAL:
        data = _load(name)
        if data:
            setattr(pack, name, data)
    return pack

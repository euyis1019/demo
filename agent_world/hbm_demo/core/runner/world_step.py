"""HBM demo WorldStep — parallel LLM decisions within each place."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_world.world.step import WorldStep, _extract_actions

log = logging.getLogger("agent_world.hbm_demo.world_step")


class HbmWorldStep(WorldStep):
    """Run co-located agents' ``perform_action_by_llm`` calls in parallel."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._tick_context: Optional[Dict[str, Any]] = None
        self._passive_ticks_batch: int = 0
        self._batch_tick_index: int = 0
        self._render_inflight: bool = False  # F18 出图单帧在途节流
        self._render_task: Optional[Any] = None  # F18 最近一次出图任务（供降 tick 等待）
        self._last_speech_by_place: Dict[str, Dict[str, int]] = {}  # F18 各房间最近发言
        self._speech_seq: int = 0  # F18 台词序号：每句新台词 +1

    def set_tick_context(
        self,
        turn_context: Optional[Dict[str, Any]],
        *,
        reset_l3_window: bool = False,
    ) -> None:
        self._tick_context = dict(turn_context) if turn_context else None
        if reset_l3_window:
            self._passive_ticks_batch = 0
            self._batch_tick_index = 0

    def clear_tick_context(self) -> None:
        self._tick_context = None
        self._passive_ticks_batch = 0
        self._batch_tick_index = 0

    async def run_one_tick(self) -> Dict[str, Any]:
        result = await super().run_one_tick()
        if self._tick_context is not None and self._tick_context.get("player_inject_tick") is None:
            self._batch_tick_index += 1
        self._maybe_render_frame(int(self.world.clock.t))
        return result

    # ------------------------------------------------------------------ #
    # F18 场景渲染 hook（经 integration 桥接，D4）                          #
    # ------------------------------------------------------------------ #
    def _note_speech_for_render(self, agent_id: Any, atype: Any, akwargs: Dict[str, Any]) -> None:
        """记录"某房间最近谁说了话"，供 F18 出图时体现说话人 + 台词更新。"""
        aname = getattr(atype, "name", str(atype)).upper()
        if "SPEAK" not in aname:
            return
        if not (akwargs.get("content") or akwargs.get("text")):
            return
        try:
            aid = int(agent_id)
        except (TypeError, ValueError):
            return
        place = self._agent_place_id(aid)
        if not place:
            return
        self._speech_seq += 1
        self._last_speech_by_place[place] = {"speaker": aid, "seq": self._speech_seq}

    def _build_scene(self, t: int):
        from agent_world.hbm_demo.core.runner.integration import scene_render

        player_place = self.world.location_of(0)
        occupants = self.world.agents_at(player_place) if player_place else set()
        occupant_count = len(occupants)
        phase = self._tick_context.get("phase") if self._tick_context else None
        last = self._last_speech_by_place.get(player_place or "")
        speaker_id = last["speaker"] if last else None
        line_seq = last["seq"] if last else 0
        return scene_render.SceneState(
            tick=int(t),
            place=player_place or "default",
            phase=phase,
            occupant_count=occupant_count,
            has_speaker=speaker_id is not None or occupant_count > 1,
            speaker_id=speaker_id,
            line_seq=line_seq,
        )

    def _maybe_render_frame(self, t: int) -> None:
        """tick 定型后异步出一帧；单帧在途时跳过（天然节流，不阻塞世界逻辑）。"""
        if self.world_db is None or self._render_inflight:
            return
        try:
            from agent_world.hbm_demo.core.runner.integration import scene_render

            if not scene_render.is_enabled():
                return
            sim_dir = Path(self.world_db.path).parent  # world_db.path 是 str
            scene = self._build_scene(t)
            self._render_inflight = True
            self._render_task = asyncio.create_task(self._render_frame_task(scene, sim_dir))
        except Exception as exc:  # 出图编排失败绝不拖垮 tick
            self._render_inflight = False
            log.warning("F18 render dispatch failed at t=%s: %s", t, exc)

    async def render_opening_frame(self, max_attempts: int = 2) -> None:
        """开局先出一帧：不依赖世界推进，启动即渲染当前场景一帧并落盘（带重试）。"""
        if self.world_db is None or self._render_inflight:
            return
        try:
            from agent_world.hbm_demo.core.runner.integration import scene_render

            if not scene_render.is_enabled():
                return
            sim_dir = Path(self.world_db.path).parent
            scene = self._build_scene(int(self.world.clock.t))
            self._render_inflight = True
        except Exception as exc:
            self._render_inflight = False
            log.warning("F18 opening frame setup failed: %s", exc)
            return
        try:
            for attempt in range(max(1, max_attempts)):
                result = await scene_render.render_scene_frame_async(scene)
                if result.ok and result.image_b64:
                    scene_render.write_latest_frame(
                        sim_dir, result.tick, result.image_b64, result.mime
                    )
                    log.info("F18 opening frame ready at t=%s", result.tick)
                    return
                log.warning(
                    "F18 opening frame attempt %d/%d failed: %s",
                    attempt + 1, max_attempts, result.error,
                )
        except Exception as exc:
            log.warning("F18 opening frame failed: %s", exc)
        finally:
            self._render_inflight = False

    async def await_render(self, timeout: float) -> None:
        """降 tick 匹配：等当前帧出完再进下一 tick；超时则让任务后台续跑（画面滞后）。"""
        task = self._render_task
        if task is None or task.done():
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except asyncio.TimeoutError:
            pass  # 超过上限：不阻塞世界，帧稍后写入（滞后一两拍）
        except Exception:
            pass  # 出图任务自身异常已在任务内兜底

    async def _render_frame_task(self, scene, sim_dir) -> None:
        from agent_world.hbm_demo.core.runner.integration import scene_render

        try:
            result = await scene_render.render_scene_frame_async(scene)
            if result.ok and result.image_b64:
                scene_render.write_latest_frame(
                    sim_dir, result.tick, result.image_b64, result.mime
                )
            else:
                log.debug("F18 frame t=%s skipped: %s", scene.tick, result.error)
        except Exception as exc:
            log.warning("F18 render task failed t=%s: %s", scene.tick, exc)
        finally:
            self._render_inflight = False

    def _pick_active(self, t: int) -> List[int]:
        from agent_world.hbm_demo.core.runner.integration import abcs

        if not abcs.is_f07_enabled() or not self._tick_context:
            if abcs.is_world_loop_enabled():
                ctx = abcs.bootstrap_mirror()
                return abcs.pick_active_ids(ctx, self.world, t, batch_tick_index=999)
            return super()._pick_active(t)

        ctx = self._tick_context
        batch_tick_index = self._batch_tick_index
        inject_tick = ctx.get("player_inject_tick")
        if inject_tick is not None:
            batch_tick_index = max(0, int(t) - int(inject_tick))

        primary = set(abcs.primary_active_ids(ctx))
        active = abcs.pick_active_ids(
            ctx,
            self.world,
            t,
            passive_ticks_so_far=self._passive_ticks_batch,
            batch_tick_index=batch_tick_index,
        )
        passive_added = [aid for aid in active if aid not in primary]
        if passive_added:
            self._passive_ticks_batch += 1
        return active

    def _agent_place_id(self, agent_id: int) -> Optional[str]:
        """Place id for F15 links and player-facing F2F emission."""
        return self._location_of(int(agent_id))

    async def _run_single_agent(self, agent_id: int, t: int) -> None:
        agent = self._resolve_agent(agent_id)
        if agent is None:
            return

        ctx = self._tick_context
        if ctx:
            agent._batch_turn_context = ctx  # noqa: SLF001
            llm = dict(ctx.get("llm_params") or {})
            if llm:
                agent._batch_temperature = llm.get("temperature")  # noqa: SLF001
                agent._batch_max_tokens = llm.get("max_tokens")  # noqa: SLF001

        prompt_trace_id: Optional[str] = None
        try:
            decision = await self._decide(agent, agent_id, t)
        finally:
            prompt_trace_id = getattr(agent, "_prompt_trace_id", None)
            agent._prompt_trace_id = None  # noqa: SLF001
            if ctx:
                agent._batch_turn_context = None  # noqa: SLF001
                agent._batch_temperature = None  # noqa: SLF001
                agent._batch_max_tokens = None  # noqa: SLF001

        if decision is None or isinstance(decision, Exception):
            if isinstance(decision, Exception):
                log.warning("agent %s decide failed: %s", agent_id, decision)
            return

        for atype, akwargs in _extract_actions(decision):
            try:
                dispatch_result = await self.dispatcher.dispatch(
                    agent_id, atype, t, **(akwargs or {})
                )
                from agent_world.hbm_demo.core.runner.integration import prompt_trace

                await prompt_trace.record_action_links(
                    self.world_db,
                    trace_id=prompt_trace_id,
                    agent_id=int(agent_id),
                    t=int(t),
                    action_type=atype,
                    action_kwargs=akwargs or {},
                    dispatch_result=dispatch_result,
                    place_id=self._agent_place_id(agent_id),
                )
                from agent_world.hbm_demo.core.runner.integration import abcs

                agent = self._resolve_agent(agent_id)
                if agent is not None:
                    abcs.mark_communication_action(
                        agent,
                        action_type=atype,
                        action_kwargs=akwargs or {},
                        dispatch_result=dispatch_result,
                        t=int(t),
                    )
                await self._handle_speak_to_local_f2f(
                    agent_id=agent_id,
                    action_type=atype,
                    action_kwargs=akwargs or {},
                    dispatch_result=dispatch_result,
                    t=t,
                )
                self._note_speech_for_render(agent_id, atype, akwargs or {})
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "dispatch(agent=%s, action=%s) failed: %s",
                    agent_id,
                    atype,
                    exc,
                )

    async def _handle_speak_to_local_f2f(
        self,
        *,
        agent_id: int,
        action_type: Any,
        action_kwargs: Dict[str, Any],
        dispatch_result: Any,
        t: int,
    ) -> None:
        from agent_world.hbm_demo.core.runner.integration import abcs

        if not abcs.is_speak_to_local_action(action_type):
            return
        if not dispatch_result or not dispatch_result.get("success"):
            return

        if abcs.bus_delivered_player_facing_f2f(dispatch_result):
            return

        content = str(action_kwargs.get("content") or "").strip()
        if not content:
            return
        place_id = self._agent_place_id(agent_id)
        if not place_id or self.world_db is None:
            return
        try:
            await abcs.emit_player_facing_f2f(
                self.world_db,
                sender_id=int(agent_id),
                place_id=str(place_id),
                content=content,
                t=int(t),
            )
            log.debug(
                "F07-E0 player_facing_f2f agent=%s place=%s t=%s",
                agent_id,
                place_id,
                t,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "player_facing_f2f failed agent=%s: %s",
                agent_id,
                exc,
            )

    async def _run_place(
        self, place_id: str, agent_ids: List[int], t: int
    ) -> None:
        if not agent_ids:
            return
        if len(agent_ids) == 1:
            await self._run_single_agent(agent_ids[0], t)
            return

        results = await asyncio.gather(
            *[self._run_single_agent(aid, t) for aid in agent_ids],
            return_exceptions=True,
        )
        for aid, result in zip(agent_ids, results):
            if isinstance(result, Exception):
                log.error(
                    "parallel _run_place(%s) agent=%s raised: %s",
                    place_id,
                    aid,
                    result,
                )

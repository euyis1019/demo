import { useMemo, useState, type ReactNode } from "react";
import type { GameMessage, Onboarding, StatDimension, Stats, WorldEvent } from "../../api/types";
import type { AgentInbox } from "../../store/agentInbox";
import { agentsInPlace } from "../../store/worldSync";
import type { PlaceId } from "../../utils/places";
import { placeDisplayName } from "../../utils/places";
import { WorldEventModal } from "../world-stage";
import { storyPlaceBackground } from "./storyAssets";
import { StoryPlaceList } from "./StoryPlaceList";
import { StoryRoomRoster } from "./StoryRoomRoster";
import { StoryPlayerPhone } from "./StoryPlayerPhone";
import { StoryBriefPanel } from "./StoryBriefPanel";
import { StoryStatsHud } from "./StoryStatsHud";
import { StorySubtitle } from "./StorySubtitle";
import { StoryDialogueHistory } from "./StoryDialogueHistory";
import { StoryModeToolbar } from "./StoryModeToolbar";
import type { ViewMode } from "./viewMode";
import { playerRoomMessages, useStoryDialogueQueue } from "./useStoryDialogue";

export interface StoryModeStageProps {
  viewMode: ViewMode;
  placeId: PlaceId;
  roomF2f: Record<PlaceId, GameMessage[]>;
  nameMap: Record<string, string>;
  /** 每个 agent 最新情绪标签，驱动字幕/名册立绘按情绪切换。 */
  agentMood?: Record<string, string>;
  /** agent → 位置（在场名册、移动后谁在这里）。 */
  agentLocations?: Record<string, { placeId: string; arrivedAt: number }>;
  /** 玩家(agent 0)收件箱：收到的私信/群聊。 */
  playerInbox?: AgentInbox;
  /** 世界全部地点（左侧地点列表点击移动）。 */
  places?: string[];
  /** 移动/发送禁用（非游玩中/加载时）。 */
  placesDisabled?: boolean;
  /** 玩家数值，剧情模式 HUD 显示。 */
  stats?: Stats;
  /** 属性维度定义（数据驱动：来自活跃 Story Pack 的 meta.stats）。 */
  statsDimensions?: StatDimension[];
  /** 开场引导（背景 + 此刻能做什么）——剧情模式里随手可重看，补删幕后的目标感。 */
  onboarding?: Onboarding | null;
  pendingWorldEvent: WorldEvent | null;
  lastError?: string;
  inputSlot: ReactNode;
  worldLoopState?: import("../../api/types").WorldLoopState;
  pauseDisabled?: boolean;
  resetDisabled?: boolean;
  onToggleViewMode: () => void;
  onPauseWorld?: () => void;
  onResumeWorld?: () => void;
  onReset?: () => void;
  onDismissWorldEvent: () => void;
}

export function StoryModeStage({
  viewMode,
  placeId,
  roomF2f,
  nameMap,
  agentMood,
  agentLocations,
  playerInbox,
  places,
  placesDisabled,
  stats,
  statsDimensions,
  onboarding,
  pendingWorldEvent,
  lastError,
  inputSlot,
  worldLoopState,
  pauseDisabled,
  resetDisabled,
  onToggleViewMode,
  onPauseWorld,
  onResumeWorld,
  onReset,
  onDismissWorldEvent,
}: StoryModeStageProps) {
  const roomMessages = playerRoomMessages(roomF2f, placeId);
  const dialogue = useStoryDialogueQueue(roomMessages, nameMap, agentMood);
  const backgroundUrl = storyPlaceBackground(placeId);
  // 在场名册点某个 NPC → 预选私信对象，给右上角私信栏。
  const [composeTarget, setComposeTarget] = useState<string | null>(null);

  const placeName = placeDisplayName(placeId);
  const subtitlePlaceholder = `【${placeName}】`;

  // 在场 NPC 名字 → 顶部「情境」一行的环境提示（删幕后给玩家「此刻在哪、和谁在一起」的轻指引）。
  const presentNames = useMemo(
    () =>
      agentsInPlace(agentLocations ?? {}, placeId)
        .filter((id) => id !== "player")
        .map((id) => nameMap[String(id)] ?? `Agent ${id}`),
    [agentLocations, placeId, nameMap],
  );
  const situation =
    presentNames.length > 0
      ? `${placeName} · 此刻和你在一起的：${presentNames.join("、")}`
      : `${placeName} · 此处只有你一人`;

  return (
    <div className="story-mode-stage">
      <StoryModeToolbar
        viewMode={viewMode}
        worldLoopState={worldLoopState}
        pauseDisabled={pauseDisabled}
        resetDisabled={resetDisabled}
        onToggleViewMode={onToggleViewMode}
        onPauseWorld={onPauseWorld}
        onResumeWorld={onResumeWorld}
        onReset={onReset}
        actions={
          <>
            <StoryPlayerPhone
              inbox={playerInbox}
              nameMap={nameMap}
              presetTarget={composeTarget}
              onTargetConsumed={() => setComposeTarget(null)}
              disabled={placesDisabled}
            />
            <StoryBriefPanel onboarding={onboarding} />
          </>
        }
      />

      <div
        className="story-mode-stage__background"
        style={{ backgroundImage: `url(${backgroundUrl})` }}
        role="img"
        aria-label={placeName}
      />
      <div className="story-stage__atmosphere" aria-hidden="true" />

      {/* 左列：数值 HUD + 地点列表（私信/剧情/收件箱已并入顶部工具条同排）。 */}
      {stats || (places && places.length) ? (
        <div className="story-left-col">
          {stats ? <StoryStatsHud stats={stats} dimensions={statsDimensions} /> : null}
          {places && places.length ? (
            <StoryPlaceList placeId={placeId} places={places} disabled={placesDisabled} />
          ) : null}
        </div>
      ) : null}

      {/* 顶部中央：情境一行 + 玩家台词输入框（输入框回到最上面中间）。 */}
      <div className="story-topcenter">
        <div className="story-situation" aria-live="polite">
          <span className="story-situation__dot" aria-hidden="true" />
          {situation}
        </div>
        <div className="story-topcenter__speak">{inputSlot}</div>
      </div>

      {lastError ? (
        <p className="story-mode-stage__error game-error" role="alert">
          {lastError}
        </p>
      ) : null}

      {/* 底部「舞台」带：在场立绘名册 → 字幕(对白)。台词输入已移到顶部中央。 */}
      <div className="story-bottom">
        <StoryRoomRoster
          placeId={placeId}
          agentLocations={agentLocations ?? {}}
          nameMap={nameMap}
          agentMood={agentMood}
          onPick={(id) => setComposeTarget(id)}
        />
        <StorySubtitle
          line={dialogue.line}
          placeholder={subtitlePlaceholder}
          hasNext={dialogue.hasNext}
          remaining={dialogue.remaining}
          onAdvance={dialogue.advance}
        />
      </div>

      <StoryDialogueHistory messages={roomMessages} nameMap={nameMap} placeId={placeId} />

      {pendingWorldEvent ? (
        <WorldEventModal event={pendingWorldEvent} onDismiss={onDismissWorldEvent} />
      ) : null}
    </div>
  );
}

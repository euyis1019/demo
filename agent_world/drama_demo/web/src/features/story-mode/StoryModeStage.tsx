import { useState, type ReactNode } from "react";
import type { GameMessage, StatDimension, Stats, WorldEvent } from "../../api/types";
import type { AgentInbox } from "../../store/agentInbox";
import type { PlaceId } from "../../utils/places";
import { placeDisplayName } from "../../utils/places";
import { WorldEventModal } from "../world-stage";
import { storyPlaceBackground } from "./storyAssets";
import { StoryPlayerInbox } from "./StoryPlayerInbox";
import { StoryPlaceList } from "./StoryPlaceList";
import { StoryRoomRoster } from "./StoryRoomRoster";
import { StoryComposeBar } from "./StoryComposeBar";
import { StoryPhonePanel } from "./StoryPhonePanel";
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
  /** 世界 tick / 玩家回合（手机面板显示）。 */
  worldTick?: number;
  playerTurn?: number;
  /** 玩家数值，剧情模式 HUD 显示。 */
  stats?: Stats;
  /** 属性维度定义（数据驱动：来自活跃 Story Pack 的 meta.stats）。 */
  statsDimensions?: StatDimension[];
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
  worldTick,
  playerTurn,
  stats,
  statsDimensions,
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
  // 在场名册点某个 NPC → 预选私信对象，给下方发送栏。
  const [composeTarget, setComposeTarget] = useState<string | null>(null);

  const subtitlePlaceholder = `【${placeDisplayName(placeId)}】`;

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
      />

      <div
        className="story-mode-stage__background"
        style={{ backgroundImage: `url(${backgroundUrl})` }}
        role="img"
        aria-label={placeDisplayName(placeId)}
      />

      {/* 左列：数值 HUD + 地点列表自然纵向堆叠（不再各自魔法像素定位，避免维度多时相互重叠/留洞） */}
      {(stats || (places && places.length)) ? (
        <div className="story-left-col">
          {stats ? <StoryStatsHud stats={stats} dimensions={statsDimensions} /> : null}
          {places && places.length ? (
            <StoryPlaceList placeId={placeId} places={places} disabled={placesDisabled} />
          ) : null}
        </div>
      ) : null}

      {/* #4：上帝模式手机——所在地 + 进度（在场看名册立绘、数值看左侧 HUD，不在此重复） */}
      <StoryPhonePanel
        placeLabel={placeDisplayName(placeId)}
        worldTick={worldTick}
        playerTurn={playerTurn}
      />

      {/* #5：当前地点在场 NPC 立绘名册——点头像可快速私信 */}
      <StoryRoomRoster
        placeId={placeId}
        agentLocations={agentLocations ?? {}}
        nameMap={nameMap}
        agentMood={agentMood}
        onPick={(id) => setComposeTarget(id)}
      />

      {lastError ? (
        <p className="story-mode-stage__error game-error" role="alert">
          {lastError}
        </p>
      ) : null}

      <div className="story-mode-stage__input">
        <StoryPlayerInbox inbox={playerInbox} nameMap={nameMap} />
        {/* #4：私信/群聊发送栏——收件箱下方的输入框 */}
        <StoryComposeBar
          nameMap={nameMap}
          presetTarget={composeTarget}
          onTargetConsumed={() => setComposeTarget(null)}
          disabled={placesDisabled}
        />
        {inputSlot}
      </div>

      <StorySubtitle
        line={dialogue.line}
        placeholder={subtitlePlaceholder}
        hasNext={dialogue.hasNext}
        remaining={dialogue.remaining}
        onAdvance={dialogue.advance}
      />

      <StoryDialogueHistory
        messages={roomMessages}
        nameMap={nameMap}
        placeId={placeId}
      />

      {pendingWorldEvent ? (
        <WorldEventModal event={pendingWorldEvent} onDismiss={onDismissWorldEvent} />
      ) : null}
    </div>
  );
}

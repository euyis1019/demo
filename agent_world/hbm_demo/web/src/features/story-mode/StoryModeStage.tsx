import type { ReactNode } from "react";
import type { GameMessage, Stats, WorldEvent } from "../../api/types";
import type { AgentInbox } from "../../store/agentInbox";
import type { PlaceId } from "../../utils/places";
import { placeDisplayName } from "../../utils/places";
import { WorldEventModal } from "../world-stage";
import { storyPlaceBackground } from "./storyAssets";
import { StoryPlayerInbox } from "./StoryPlayerInbox";
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
  /** 每个 agent 最新情绪标签，驱动字幕立绘按情绪切换。 */
  agentMood?: Record<string, string>;
  /** 玩家(agent 0)收件箱：收到的私信/群聊。 */
  playerInbox?: AgentInbox;
  /** 玩家数值，剧情模式 HUD 显示。 */
  stats?: Stats;
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
  playerInbox,
  stats,
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

      {stats ? <StoryStatsHud stats={stats} /> : null}

      {lastError ? (
        <p className="story-mode-stage__error game-error" role="alert">
          {lastError}
        </p>
      ) : null}

      <div className="story-mode-stage__input">
        <StoryPlayerInbox inbox={playerInbox} nameMap={nameMap} />
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

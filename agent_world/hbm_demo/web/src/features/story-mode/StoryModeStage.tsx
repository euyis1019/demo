import type { ReactNode } from "react";
import type { GameMessage, WorldEvent } from "../../api/types";
import type { PlaceId } from "../../utils/places";
import { placeDisplayName } from "../../utils/places";
import { WorldEventModal } from "../world-stage";
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
  pendingWorldEvent: WorldEvent | null;
  lastError?: string;
  inputSlot: ReactNode;
  /** F18 实时整帧画面（替换静态沉浸式背景）。 */
  frame: { tick: number; dataUri: string } | null;
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
  pendingWorldEvent,
  lastError,
  inputSlot,
  frame,
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
  const dialogue = useStoryDialogueQueue(roomMessages, nameMap);

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

      {frame ? (
        <img
          className="story-mode-stage__frame"
          src={frame.dataUri}
          alt={placeDisplayName(placeId)}
        />
      ) : (
        <div className="story-mode-stage__frame-placeholder" role="img" aria-label="生成中">
          <div className="story-mode-stage__frame-spinner" />
          <span>AI 正在生成画面…</span>
        </div>
      )}

      {lastError ? (
        <p className="story-mode-stage__error game-error" role="alert">
          {lastError}
        </p>
      ) : null}

      <div className="story-mode-stage__input">{inputSlot}</div>

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

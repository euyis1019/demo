import type { ReactNode } from "react";
import type { GameMessage, WorldEvent } from "../../api/types";
import type { PlaceId } from "../../utils/places";
import { placeDisplayName } from "../../utils/places";
import { WorldEventModal } from "../world-stage/WorldEventModal";
import { storyPlaceBackground } from "./storyAssets";
import { StorySubtitle } from "./StorySubtitle";
import { StoryModeToolbar } from "./StoryModeToolbar";
import type { ViewMode } from "./viewMode";
import { playerRoomMessages, useStoryDialogueQueue } from "./useStoryDialogue";

export interface StoryModeStageProps {
  viewMode: ViewMode;
  placeId: PlaceId;
  roomF2f: Record<PlaceId, GameMessage[]>;
  nameMap: Record<string, string>;
  pendingWorldEvent: WorldEvent | null;
  immediateMsg?: string;
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
  pendingWorldEvent,
  immediateMsg,
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
  const {
    line: dialogueLine,
    pendingCount,
    advance,
  } = useStoryDialogueQueue(roomMessages, nameMap, placeId);
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

      {lastError ? (
        <p className="story-mode-stage__error game-error" role="alert">
          {lastError}
        </p>
      ) : null}

      <div className="story-mode-stage__input">{inputSlot}</div>

      {immediateMsg ? (
        <div className="story-mode-stage__immediate" role="status">
          {immediateMsg}
        </div>
      ) : null}

      <StorySubtitle
        line={dialogueLine}
        placeholder={subtitlePlaceholder}
        pendingCount={pendingCount}
        onAdvance={advance}
      />

      {pendingWorldEvent ? (
        <WorldEventModal event={pendingWorldEvent} onDismiss={onDismissWorldEvent} />
      ) : null}
    </div>
  );
}

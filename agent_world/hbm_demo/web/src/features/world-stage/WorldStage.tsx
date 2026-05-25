import { useEffect, type ReactNode } from "react";
import type { GameMessage, WorldEvent } from "../../api/types";
import type { PlaceId } from "../../utils/places";
import type { AgentInbox } from "../../store/worldSync";
import { AgentPhoneModal } from "./AgentPhoneModal";
import { RoomGrid } from "./RoomGrid";
import { WorldEventModal } from "./WorldEventModal";

export interface WorldStageProps {
  roomF2f: Record<PlaceId, GameMessage[]>;
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>;
  agentInbox: Record<string, AgentInbox>;
  nameMap: Record<string, string>;
  recentMoveKeys: string[];
  activeAgentModal: string | null;
  pendingWorldEvent: WorldEvent | null;
  immediateMsg?: string;
  lastError?: string;
  inputSlot: ReactNode;
  onAgentClick: (agentId: string) => void;
  onCloseAgentModal: () => void;
  onDismissWorldEvent: () => void;
  onClearRecentMoves: () => void;
}

export function WorldStage({
  roomF2f,
  agentLocations,
  agentInbox,
  nameMap,
  recentMoveKeys,
  activeAgentModal,
  pendingWorldEvent,
  immediateMsg,
  lastError,
  inputSlot,
  onAgentClick,
  onCloseAgentModal,
  onDismissWorldEvent,
  onClearRecentMoves,
}: WorldStageProps) {
  useEffect(() => {
    if (recentMoveKeys.length === 0) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      onClearRecentMoves();
    }, 450);
    return () => window.clearTimeout(timer);
  }, [recentMoveKeys, onClearRecentMoves]);

  const activeInbox =
    activeAgentModal != null
      ? agentInbox[activeAgentModal] ?? {
          rdc: [],
          grp: [],
          osLog: [],
          archivedThreadKeys: [],
        }
      : null;

  return (
    <div className="world-stage">
      {immediateMsg ? (
        <div className="world-stage__immediate" role="status">
          {immediateMsg}
        </div>
      ) : null}
      {lastError ? (
        <p className="game-error world-stage__error" role="alert">
          {lastError}
        </p>
      ) : null}

      <RoomGrid
        roomF2f={roomF2f}
        agentLocations={agentLocations}
        nameMap={nameMap}
        recentMoveKeys={recentMoveKeys}
        onAgentClick={onAgentClick}
      />

      <footer className="world-stage__input">{inputSlot}</footer>

      {activeAgentModal && activeInbox ? (
        <AgentPhoneModal
          agentId={activeAgentModal}
          inbox={activeInbox}
          nameMap={nameMap}
          onClose={onCloseAgentModal}
        />
      ) : null}

      {pendingWorldEvent ? (
        <WorldEventModal event={pendingWorldEvent} onDismiss={onDismissWorldEvent} />
      ) : null}
    </div>
  );
}

import { useEffect, useCallback, type ReactNode } from "react";
import type { GameMessage, WorldEvent } from "../../../api/types";
import type { PlaceId } from "../../../utils/places";
import type { AgentInbox, RdcLink } from "../../../store/worldSync";
import { PromptTraceModal, usePromptTrace } from "../../prompt-trace";
import { AgentPhoneModal } from "./AgentPhoneModal";
import { RoomGrid } from "./RoomGrid";
import { WorldEventModal } from "./WorldEventModal";

export interface WorldStageProps {
  roomF2f: Record<PlaceId, GameMessage[]>;
  playerPlaceId: PlaceId;
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>;
  agentInbox: Record<string, AgentInbox>;
  nameMap: Record<string, string>;
  recentMoveKeys: string[];
  recentRdcLinks: RdcLink[];
  /** 故事定义的**全部**地点（含没人的空房间）——上帝模式据此默认铺满所有地点。 */
  worldPlaces?: string[];
  activeAgentModal: string | null;
  pendingWorldEvent: WorldEvent | null;
  lastError?: string;
  inputSlot: ReactNode;
  onAgentClick: (agentId: string) => void;
  onCloseAgentModal: () => void;
  onDismissWorldEvent: () => void;
  onClearRecentMoves: () => void;
  onClearRecentRdcLinks: () => void;
}

export function WorldStage({
  roomF2f,
  playerPlaceId,
  agentLocations,
  agentInbox,
  nameMap,
  recentMoveKeys,
  recentRdcLinks,
  worldPlaces,
  activeAgentModal,
  pendingWorldEvent,
  lastError,
  inputSlot,
  onAgentClick,
  onCloseAgentModal,
  onDismissWorldEvent,
  onClearRecentMoves,
  onClearRecentRdcLinks,
}: WorldStageProps) {
  const promptTrace = usePromptTrace();

  const openMessagePrompt = useCallback(
    (message: GameMessage) => {
      void promptTrace.openTrace({
        refKey: message.ref_key,
        label: `F2F · ${message.sender} @ t=${message.attempted_at ?? "?"}`,
      });
    },
    [promptTrace],
  );

  useEffect(() => {
    if (recentMoveKeys.length === 0) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      onClearRecentMoves();
    }, 450);
    return () => window.clearTimeout(timer);
  }, [recentMoveKeys, onClearRecentMoves]);

  useEffect(() => {
    if (recentRdcLinks.length === 0) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      onClearRecentRdcLinks();
    }, 4800);
    return () => window.clearTimeout(timer);
  }, [recentRdcLinks, onClearRecentRdcLinks]);

  const activeInbox =
    activeAgentModal != null
      ? agentInbox[activeAgentModal] ?? {
          rdc: [],
          grp: [],
          osLog: [],
          locationLog: [],
          archivedThreadKeys: [],
        }
      : null;

  const activeAgentPlaceId =
    activeAgentModal != null
      ? ((agentLocations[activeAgentModal]?.placeId ?? playerPlaceId) as PlaceId)
      : playerPlaceId;

  return (
    <div className="world-stage">
      {lastError ? (
        <p className="game-error world-stage__error" role="alert">
          {lastError}
        </p>
      ) : null}

      <RoomGrid
        roomF2f={roomF2f}
        playerPlaceId={playerPlaceId}
        agentLocations={agentLocations}
        nameMap={nameMap}
        recentMoveKeys={recentMoveKeys}
        recentRdcLinks={recentRdcLinks}
        worldPlaces={worldPlaces}
        onAgentClick={onAgentClick}
        onPromptClick={openMessagePrompt}
      />

      <footer className="world-stage__input">{inputSlot}</footer>

      {activeAgentModal && activeInbox ? (
        <AgentPhoneModal
          agentId={activeAgentModal}
          inbox={activeInbox}
          nameMap={nameMap}
          playerPlaceId={playerPlaceId}
          roomF2f={roomF2f[activeAgentPlaceId] ?? []}
          onClose={onCloseAgentModal}
          onOpenPromptTrace={(req) => void promptTrace.openTrace(req)}
        />
      ) : null}

      <PromptTraceModal
        open={promptTrace.open}
        loading={promptTrace.loading}
        error={promptTrace.error}
        trace={promptTrace.trace}
        noPromptReason={promptTrace.request?.noPromptReason}
        label={promptTrace.request?.label}
        nameMap={nameMap}
        onClose={promptTrace.close}
      />

      {pendingWorldEvent ? (
        <WorldEventModal event={pendingWorldEvent} onDismiss={onDismissWorldEvent} />
      ) : null}
    </div>
  );
}

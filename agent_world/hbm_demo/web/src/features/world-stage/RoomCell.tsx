import { useState } from "react";
import type { GameMessage } from "../../api/types";
import { placeDisplayName, type PlaceId } from "../../utils/places";
import { agentsInPlace } from "../../store/worldSync";
import { AgentCircle } from "./AgentCircle";
import { RoomHistoryModal } from "./RoomHistoryModal";
import { useRoomEphemeralSpeeches } from "./useRoomEphemeralSpeeches";

export interface RoomCellProps {
  placeId: PlaceId;
  messages: GameMessage[];
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>;
  nameMap: Record<string, string>;
  recentMoveKeys: string[];
  onAgentClick: (agentId: string) => void;
  onPromptClick?: (message: GameMessage) => void;
}

export function RoomCell({
  placeId,
  messages,
  agentLocations,
  nameMap,
  recentMoveKeys,
  onAgentClick,
  onPromptClick,
}: RoomCellProps) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const agents = agentsInPlace(agentLocations, placeId);
  const ephemeralSpeeches = useRoomEphemeralSpeeches(messages, agents, nameMap);

  return (
    <div className="room-cell" data-place-id={placeId}>
      <header className="room-cell__header">
        <button
          type="button"
          className="room-cell__history-btn"
          aria-label={`${placeDisplayName(placeId)} 聊天记录`}
          title="聊天记录"
          onClick={() => setHistoryOpen(true)}
        >
          历史
        </button>
        <span className="room-cell__title">{placeDisplayName(placeId)}</span>
      </header>
      <div className="room-cell__stage">
        <div className="room-cell__agents">
          {agents.map((agentId, index) => (
            <AgentCircle
              key={agentId}
              agentId={agentId}
              index={index}
              total={agents.length}
              nameMap={nameMap}
              recentMoveKeys={recentMoveKeys}
              speechContent={ephemeralSpeeches[agentId]?.content}
              onClick={onAgentClick}
            />
          ))}
          {agents.length === 0 ? (
            <p className="room-cell__empty">暂无 Agent</p>
          ) : null}
        </div>
      </div>

      {historyOpen ? (
        <RoomHistoryModal
          placeId={placeId}
          messages={messages}
          nameMap={nameMap}
          onClose={() => setHistoryOpen(false)}
          onPromptClick={onPromptClick}
        />
      ) : null}
    </div>
  );
}

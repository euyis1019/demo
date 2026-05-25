import type { GameMessage } from "../../api/types";
import { agentDisplayName } from "../../constants/agents";
import { placeDisplayName, type PlaceId } from "../../utils/places";
import { agentsInPlace } from "../../store/worldSync";
import { AgentCircle } from "./AgentCircle";
import { RoomSpeechBubble } from "./RoomSpeechBubble";

export interface RoomCellProps {
  placeId: PlaceId;
  messages: GameMessage[];
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>;
  nameMap: Record<string, string>;
  recentMoveKeys: string[];
  onAgentClick: (agentId: string) => void;
}

export function RoomCell({
  placeId,
  messages,
  agentLocations,
  nameMap,
  recentMoveKeys,
  onAgentClick,
}: RoomCellProps) {
  const agents = agentsInPlace(agentLocations, placeId);

  return (
    <div className="room-cell" data-place-id={placeId}>
      <header className="room-cell__header">{placeDisplayName(placeId)}</header>
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
              onClick={onAgentClick}
            />
          ))}
          {agents.length === 0 ? (
            <p className="room-cell__empty">暂无 Agent</p>
          ) : null}
        </div>
        <RoomSpeechBubble messages={messages} />
      </div>
    </div>
  );
}

export { agentDisplayName };

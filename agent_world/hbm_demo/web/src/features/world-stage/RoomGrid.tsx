import type { GameMessage } from "../../api/types";
import type { PlaceId } from "../../utils/places";
import { ROOM_GRID } from "../../utils/places";
import type { RdcLink } from "../../store/worldSync";
import { RoomCell } from "./RoomCell";
import { RdcConnectionOverlay } from "./RdcConnectionOverlay";

export interface RoomGridProps {
  roomF2f: Record<PlaceId, GameMessage[]>;
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>;
  nameMap: Record<string, string>;
  recentMoveKeys: string[];
  recentRdcLinks: RdcLink[];
  onAgentClick: (agentId: string) => void;
  onPromptClick?: (message: GameMessage) => void;
}

/** 2×2 四房间 grid（dev_logs/32 §6.3）。 */
export function RoomGrid({
  roomF2f,
  agentLocations,
  nameMap,
  recentMoveKeys,
  recentRdcLinks,
  onAgentClick,
  onPromptClick,
}: RoomGridProps) {
  return (
    <div className="room-grid" role="grid" aria-label="四房间世界视图">
      {ROOM_GRID.map((placeId) => (
        <RoomCell
          key={placeId}
          placeId={placeId}
          messages={roomF2f[placeId] ?? []}
          agentLocations={agentLocations}
          nameMap={nameMap}
          recentMoveKeys={recentMoveKeys}
          onAgentClick={onAgentClick}
          onPromptClick={onPromptClick}
        />
      ))}
      <RdcConnectionOverlay links={recentRdcLinks} agentLocations={agentLocations} />
    </div>
  );
}

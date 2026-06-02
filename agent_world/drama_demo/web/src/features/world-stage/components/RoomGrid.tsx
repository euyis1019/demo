import type { CSSProperties } from "react";
import type { GameMessage } from "../../../api/types";
import { deriveWorldPlaces } from "../../../utils/places";
import type { RdcLink } from "../../../store/worldSync";
import { RoomCell } from "./RoomCell";
import { RdcConnectionOverlay } from "./RdcConnectionOverlay";

export interface RoomGridProps {
  roomF2f: Record<string, GameMessage[]>;
  playerPlaceId: string;
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>;
  nameMap: Record<string, string>;
  recentMoveKeys: string[];
  recentRdcLinks: RdcLink[];
  /** 故事定义的**全部**地点（含没人的空房间）。上帝模式默认铺满所有地点；缺省时退回「有人的地点」。 */
  worldPlaces?: string[];
  onAgentClick: (agentId: string) => void;
  onPromptClick?: (message: GameMessage) => void;
}

/** 世界房间网格：按后端报来的真实地点动态渲染，房间数自适应（n 个地点排成近似方阵）。 */
export function RoomGrid({
  roomF2f,
  playerPlaceId,
  agentLocations,
  nameMap,
  recentMoveKeys,
  recentRdcLinks,
  worldPlaces,
  onAgentClick,
  onPromptClick,
}: RoomGridProps) {
  // 上帝模式默认显示**全部**地点（即便该地点此刻没人）；后端还没下发 worldPlaces 时退回「有人的地点」。
  const places =
    worldPlaces && worldPlaces.length
      ? worldPlaces
      : deriveWorldPlaces(playerPlaceId, agentLocations, roomF2f);
  const count = Math.max(1, places.length);
  const cols = Math.ceil(Math.sqrt(count));
  const rows = Math.ceil(count / cols);

  return (
    <div
      className="room-grid"
      role="grid"
      aria-label="世界视图"
      style={{ "--room-cols": cols, "--room-rows": rows } as CSSProperties}
    >
      {places.map((placeId) => (
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
      <RdcConnectionOverlay
        links={recentRdcLinks}
        agentLocations={agentLocations}
        places={places}
        cols={cols}
        rows={rows}
      />
    </div>
  );
}

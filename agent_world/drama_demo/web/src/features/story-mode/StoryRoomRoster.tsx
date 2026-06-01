import { ChromaKeyAvatar } from "./ChromaKeyAvatar";
import { storyAvatarBaseUrl, storyAvatarUrl } from "./storyAssets";
import { agentsInPlace } from "../../store/worldSync";

export interface StoryRoomRosterProps {
  /** 当前地点。 */
  placeId: string;
  /** agent → 位置（判断谁在场）。 */
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>;
  /** agent id → 名称。 */
  nameMap: Record<string, string>;
  /** agent id → 最新情绪（立绘按情绪切）。 */
  agentMood?: Record<string, string>;
  /** 点某个在场 NPC（用于快速私信）。 */
  onPick?: (agentId: string) => void;
}

function nameOf(id: string, nameMap: Record<string, string>): string {
  return nameMap[String(id)] ?? `Agent ${id}`;
}

/**
 * 当前地点「在场 NPC 名册」（#5）：玩家走到一个地点，就能看到这里有谁——一排小立绘头像 + 名字。
 * 配合自由移动：换地点时这排会随之更新（数据来自 agentLocations）。点头像可快速私信该 NPC。
 */
export function StoryRoomRoster({ placeId, agentLocations, nameMap, agentMood, onPick }: StoryRoomRosterProps) {
  const ids = agentsInPlace(agentLocations, placeId).filter((id) => id !== "player");
  if (!ids.length) {
    return <div className="story-roster story-roster--empty">这里暂时没有别人</div>;
  }
  return (
    <div className="story-roster" role="list" aria-label="在场人物">
      {ids.map((id) => {
        const mood = agentMood?.[id];
        const name = nameOf(id, nameMap);
        return (
          <button
            key={id}
            type="button"
            role="listitem"
            className="story-roster__chip"
            title={`私信 ${name}`}
            onClick={() => onPick?.(id)}
          >
            <span className="story-roster__avatar">
              <ChromaKeyAvatar
                src={storyAvatarUrl(id, mood)}
                fallbackSrc={storyAvatarBaseUrl(id)}
                className="story-roster__img"
              />
            </span>
            <span className="story-roster__name">{name}</span>
          </button>
        );
      })}
    </div>
  );
}

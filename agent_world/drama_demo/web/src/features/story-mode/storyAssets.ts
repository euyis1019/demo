import { API_ROOT, getSimId } from "../../api/config";
import { PLAYER_AGENT_ID } from "../../constants/agents";

/**
 * 剧情模式图片资源 = 当前激活故事在设计期由 Artist 出好、落在
 * config/stories/<story_id>/assets/ 的图，经 Flask 只读路由
 * `/api/drama/stories/<story_id>/assets/...` 提供（见 http/routes.py story_asset）。
 * 这里按 place_id / agent_id 拼 URL；缺图时由 ChromaKeyAvatar / 背景容器回退占位。
 */
function assetsBase(): string {
  return `${API_ROOT}/api/drama/stories/${encodeURIComponent(getSimId())}/assets`;
}

/** 地点背景（空镜、无人物）：按 place_id 取 assets/places/<place_id>.png。 */
export function storyPlaceBackground(placeId: string): string {
  return `${assetsBase()}/places/${encodeURIComponent(placeId)}.png`;
}

/** 基础立绘（一 agent 一张，无情绪维度）；玩家走 player.png（通常无此图，回退为空）。 */
export function storyAvatarBaseUrl(speakerId: string): string {
  if (speakerId === PLAYER_AGENT_ID) {
    return `${assetsBase()}/avatars/player.png`;
  }
  return `${assetsBase()}/avatars/agent_${speakerId}.png`;
}

/**
 * 立绘 URL。给了非 neutral 情绪标签时返回情绪变体 `agent_{id}_{mood}.png`，
 * 缺该变体图时由 ChromaKeyAvatar 的 fallbackSrc 回退到基础立绘（见 storyAvatarBaseUrl）。
 */
export function storyAvatarUrl(speakerId: string, mood?: string): string {
  if (speakerId !== PLAYER_AGENT_ID && mood && mood !== "neutral") {
    return `${assetsBase()}/avatars/agent_${speakerId}_${encodeURIComponent(mood)}.png`;
  }
  return storyAvatarBaseUrl(speakerId);
}

/** 受控情绪枚举（对齐后端 shared/emotion.py EMOTIONS）；立绘变体图按此命名 agent_{id}_{emotion}.png。 */
export const STORY_EMOTIONS = [
  "neutral",
  "happy",
  "angry",
  "sad",
  "anxious",
  "confident",
] as const;

/** 一个 agent 的全部立绘 url（基础 + 各非 neutral 情绪变体），供预热缓存——开口时瞬时切换、与字幕同步。 */
export function storyAvatarVariantUrls(speakerId: string): string[] {
  if (speakerId === PLAYER_AGENT_ID) {
    return [storyAvatarBaseUrl(speakerId)];
  }
  return [
    storyAvatarBaseUrl(speakerId),
    ...STORY_EMOTIONS.filter((e) => e !== "neutral").map((e) =>
      storyAvatarUrl(speakerId, e),
    ),
  ];
}

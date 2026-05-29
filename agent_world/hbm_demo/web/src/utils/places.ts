/** place_id → 中文展示名 + F12 四房间 grid（dev_logs/32 §6.2）。 */

export const ROOM_GRID = [
  "nvidia_reception",
  "jensen_private_room",
  "negotiation_room",
  "openai_hq",
] as const;

export type PlaceId = (typeof ROOM_GRID)[number];

const PLACE_LABELS: Record<string, string> = {
  nvidia_reception: "暗黑心理诊所 · 候诊前台",
  jensen_private_room: "Morgen 诊疗室",
  negotiation_room: "诅咒测评间",
  openai_hq: "记忆档案室",
};

export function placeDisplayName(placeId: string): string {
  return PLACE_LABELS[placeId] ?? placeId;
}

export function emptyRoomF2f(): Record<PlaceId, import("../api/types").GameMessage[]> {
  return {
    nvidia_reception: [],
    jensen_private_room: [],
    negotiation_room: [],
    openai_hq: [],
  };
}

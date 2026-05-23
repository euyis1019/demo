/** place_id → 中文展示名（与 hbm_scenario.yaml summary 对齐）。 */

const PLACE_LABELS: Record<string, string> = {
  nvidia_reception: "英伟达总部 · 接待前台",
  jensen_private_room: "黄仁勋私人会议室",
  negotiation_room: "HBM 主谈判室",
  openai_hq: "OpenAI 硅谷总部",
};

export function placeDisplayName(placeId: string): string {
  return PLACE_LABELS[placeId] ?? placeId;
}

export type EndingId =
  | "ending_join_nvidia"
  | "ending_seed_round"
  | "ending_cold_deal";

const ENDING_COPY: Record<
  EndingId,
  { title: string; description: string; badge: string }
> = {
  ending_join_nvidia: {
    badge: "结局 A",
    title: "加入 NVIDIA",
    description: "Jensen 向你伸出手：「Welcome to the NVIDIA family.」",
  },
  ending_seed_round: {
    badge: "结局 B",
    title: "独立融资",
    description: "你保留算法主权，拿到一笔可观的 seed round。",
  },
  ending_cold_deal: {
    badge: "结局 C",
    title: "冷处理协议",
    description: "信任不足，双方签下一纸冷冰冰的有限合作备忘录。",
  },
};

export interface EndingScreenProps {
  endingId: EndingId;
  onRestart?: () => void;
}

/** F2-6 — Turn 25 结局静态占位（F4 接 completed）。 */
export function EndingScreen({ endingId, onRestart }: EndingScreenProps) {
  const copy = ENDING_COPY[endingId];

  return (
    <div className="screen-overlay ending-screen ending-screen--good" role="dialog">
      <div className="ending-screen__card">
        <p className="ending-screen__badge">{copy.badge}</p>
        <h1 className="ending-screen__title">{copy.title}</h1>
        <p className="ending-screen__desc">{copy.description}</p>
        {onRestart ? (
          <button type="button" className="btn btn--primary" onClick={onRestart}>
            重新开始
          </button>
        ) : null}
      </div>
    </div>
  );
}

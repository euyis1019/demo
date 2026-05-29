export type EndingId =
  | "ending_dead_type"
  | "ending_monkey_type"
  | "ending_scarecrow_type";

const ENDING_COPY: Record<
  EndingId,
  { title: string; description: string; badge: string }
> = {
  ending_dead_type: {
    badge: "结局 A",
    title: "死者型 · 社交幽灵认证",
    description: "Morgen 合上小本本：「你不是不合群，你只是提前进入省电模式。」",
  },
  ending_monkey_type: {
    badge: "结局 B",
    title: "吗喽型 · 间歇性勇敢",
    description: "收音机嗞了一声：「恭喜，你敢发五块钱，但不敢回在吗。」",
  },
  ending_scarecrow_type: {
    badge: "结局 C",
    title: "握草人型 · 嘴硬归档",
    description: "黑猫翻了个白眼：「你的人格不是复杂，是还没加载完。」",
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

/** 结局屏：完全数据驱动——标题/好坏来自后端按故事下发的 ending summary/kind，不写死任何故事的结局。 */

export type EndingId = string;

const KIND_BADGE: Record<string, string> = {
  good: "美满结局",
  neutral: "故事落幕",
  bad: "遗憾结局",
};

export interface EndingScreenProps {
  endingId: string;
  /** 该结局的一句话描述（后端下发）。 */
  summary?: string;
  /** good | neutral | bad。 */
  kind?: string;
  onRestart?: () => void;
}

export function EndingScreen({ summary, kind, onRestart }: EndingScreenProps) {
  const badge = KIND_BADGE[kind ?? ""] ?? "故事落幕";
  const variant = kind === "bad" ? "ending-screen--bad" : "ending-screen--good";

  return (
    <div className={`screen-overlay ending-screen ${variant}`} role="dialog">
      <div className="ending-screen__card">
        <p className="ending-screen__badge">{badge}</p>
        <h1 className="ending-screen__title">{summary || "故事就此落幕"}</h1>
        {onRestart ? (
          <button type="button" className="btn btn--primary" onClick={onRestart}>
            重新开始
          </button>
        ) : null}
      </div>
    </div>
  );
}

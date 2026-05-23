export interface GameOverScreenProps {
  onRestart?: () => void;
  title?: string;
  description?: string;
}

/** F2-6 — Bad End 静态占位（F4 接 game_over）。 */
export function GameOverScreen({
  onRestart,
  title = "Bad End · 被请出大楼",
  description = "你的技术阐述未能通过前台筛选，保安礼貌地请你离开 NVIDIA 总部。",
}: GameOverScreenProps) {
  return (
    <div className="screen-overlay ending-screen ending-screen--bad" role="dialog">
      <div className="ending-screen__card">
        <p className="ending-screen__badge">GAME OVER</p>
        <h1 className="ending-screen__title">{title}</h1>
        <p className="ending-screen__desc">{description}</p>
        {onRestart ? (
          <button type="button" className="btn btn--primary" onClick={onRestart}>
            重新开始
          </button>
        ) : null}
      </div>
    </div>
  );
}

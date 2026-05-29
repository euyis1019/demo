export interface GameOverScreenProps {
  onRestart?: () => void;
  title?: string;
  description?: string;
}

/** F2-6 — Bad End 静态占位（F4 接 game_over）。 */
export function GameOverScreen({
  onRestart,
  title = "Bad End · 未通过候诊区",
  description = "你在候诊区把测试聊成了 Wi-Fi 报修，前台礼貌地把你归为「未开始就结束」。",
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

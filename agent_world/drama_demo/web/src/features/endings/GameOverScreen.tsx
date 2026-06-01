export interface GameOverScreenProps {
  onRestart?: () => void;
  title?: string;
  description?: string;
}

/** Bad End 屏：标题/描述数据驱动（由后端结局 summary 传入），不写死任何故事文案。 */
export function GameOverScreen({
  onRestart,
  title = "游戏结束",
  description = "故事在此走向了一个遗憾的结局。",
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

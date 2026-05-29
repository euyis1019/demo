export interface BootScreenProps {
  onStart?: () => void;
  onRetryHealth?: () => void;
  runnerReady?: boolean;
  message?: string;
}

/** F2-5 — 启动屏（F3 接 useHealthCheck + session/start）。 */
export function BootScreen({
  onStart,
  onRetryHealth,
  runnerReady = true,
  message = "黑色幽默 SBTI 测试 · 每次选择都会被记住",
}: BootScreenProps) {
  return (
    <div className="screen-overlay boot-screen" role="dialog" aria-modal="true">
      <div className="boot-screen__card">
        <h1 className="boot-screen__title">暗黑心理诊所</h1>
        <p className="boot-screen__subtitle">{message}</p>
        {!runnerReady ? (
          <p className="boot-screen__warn">
            Runner 未就绪，请先启动 <code>run_hbm</code> 后再试。可点击下方「复制启动命令」或「重新检测
            Runner」。
          </p>
        ) : null}
        <div className="boot-screen__actions">
          <button
            type="button"
            className="btn btn--primary"
            onClick={onStart}
            disabled={!runnerReady}
          >
            开始游戏
          </button>
          {onRetryHealth ? (
            <button
              type="button"
              className="btn btn--ghost"
              onClick={onRetryHealth}
            >
              重新检测 Runner
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

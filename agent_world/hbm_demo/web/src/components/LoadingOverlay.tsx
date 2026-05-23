export interface LoadingOverlayProps {
  visible: boolean;
  message?: string;
  elapsedSeconds?: number;
}

/** F2-5 — 轮询 / 长请求 loading（F5 接 elapsed 与禁用输入）。 */
export function LoadingOverlay({
  visible,
  message = "Agent 世界运转中…",
  elapsedSeconds,
}: LoadingOverlayProps) {
  if (!visible) {
    return null;
  }

  return (
    <div className="loading-overlay" role="status" aria-live="polite">
      <div className="loading-overlay__card">
        <div className="loading-overlay__spinner" aria-hidden="true" />
        <p className="loading-overlay__text">{message}</p>
        {elapsedSeconds !== undefined ? (
          <p className="loading-overlay__elapsed">已等待 {elapsedSeconds}s</p>
        ) : null}
      </div>
    </div>
  );
}

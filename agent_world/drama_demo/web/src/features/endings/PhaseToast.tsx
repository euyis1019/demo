import { useEffect } from "react";

export interface PhaseToastProps {
  message: string | null | undefined;
  onDismiss: () => void;
  durationMs?: number;
}

/** F4-6 — Phase 切换过渡文案 Toast。 */
export function PhaseToast({
  message,
  onDismiss,
  durationMs = 4500,
}: PhaseToastProps) {
  useEffect(() => {
    if (!message) {
      return undefined;
    }
    const timer = setTimeout(onDismiss, durationMs);
    return () => clearTimeout(timer);
  }, [message, onDismiss, durationMs]);

  if (!message) {
    return null;
  }

  return (
    <div className="phase-toast" role="status" aria-live="polite">
      <p className="phase-toast__text">{message}</p>
      <button
        type="button"
        className="phase-toast__close"
        onClick={onDismiss}
        aria-label="关闭"
      >
        ×
      </button>
    </div>
  );
}

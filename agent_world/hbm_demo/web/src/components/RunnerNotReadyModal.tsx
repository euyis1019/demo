import { useCallback, useState } from "react";
import { RUN_HBM_COMMAND } from "../constants/runner";

export interface RunnerNotReadyModalProps {
  open: boolean;
  onClose: () => void;
  onRetryHealth?: () => void;
  command?: string;
  detail?: string;
}

/** F5-2 — 503 Runner 未就绪 Modal，可复制 run_hbm 命令。 */
export function RunnerNotReadyModal({
  open,
  onClose,
  onRetryHealth,
  command = RUN_HBM_COMMAND,
  detail = "Runner 未就绪或 world.db 不可读。请在仓库根目录启动 run_hbm，并确保 Flask 使用同一 sim_dir。",
}: RunnerNotReadyModalProps) {
  const [copied, setCopied] = useState(false);

  const copyCommand = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }, [command]);

  if (!open) {
    return null;
  }

  return (
    <div className="modal-overlay runner-modal" role="dialog" aria-modal="true">
      <div className="runner-modal__card">
        <h2 className="runner-modal__title">Runner 未就绪</h2>
        <p className="runner-modal__desc">{detail}</p>
        <pre className="runner-modal__command">{command}</pre>
        <div className="runner-modal__actions">
          <button type="button" className="btn btn--primary" onClick={() => void copyCommand()}>
            {copied ? "已复制" : "复制启动命令"}
          </button>
          {onRetryHealth ? (
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => {
                onRetryHealth();
                onClose();
              }}
            >
              重新检测
            </button>
          ) : null}
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}

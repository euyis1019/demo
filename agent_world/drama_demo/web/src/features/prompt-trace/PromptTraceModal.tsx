import { useState } from "react";
import type { PromptTraceData } from "../../api/types";
import { agentDisplayName } from "../../constants/agents";

export interface PromptTraceModalProps {
  open: boolean;
  loading: boolean;
  error: string | null;
  trace: PromptTraceData | null;
  noPromptReason?: string | null;
  label?: string | null;
  nameMap: Record<string, string>;
  onClose: () => void;
}

type TabId = "system" | "user" | "tools";

export function PromptTraceModal({
  open,
  loading,
  error,
  trace,
  noPromptReason,
  label,
  nameMap,
  onClose,
}: PromptTraceModalProps) {
  const [tab, setTab] = useState<TabId>("system");

  if (!open) {
    return null;
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="prompt-trace-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Prompt 调试"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="prompt-trace-modal__header">
          <div>
            <h2>Prompt Inspector</h2>
            <p className="prompt-trace-modal__subtitle">
              {label ?? "LLM 决策追溯"}
            </p>
          </div>
          <button type="button" className="modal-close" onClick={onClose}>
            关闭
          </button>
        </header>

        {noPromptReason ? (
          <div className="prompt-trace-modal__body">
            <p className="prompt-trace-modal__notice">{noPromptReason}</p>
          </div>
        ) : null}

        {!noPromptReason && loading ? (
          <div className="prompt-trace-modal__body">
            <p className="prompt-trace-modal__notice">正在加载 Prompt…</p>
          </div>
        ) : null}

        {!noPromptReason && error ? (
          <div className="prompt-trace-modal__body">
            <p className="prompt-trace-modal__error" role="alert">
              {error}
            </p>
          </div>
        ) : null}

        {!noPromptReason && trace ? (
          <>
            <dl className="prompt-trace-modal__meta">
              <div>
                <dt>Agent</dt>
                <dd>{agentDisplayName(String(trace.agent_id), nameMap)}</dd>
              </div>
              <div>
                <dt>Tick</dt>
                <dd>{trace.at_tick}</dd>
              </div>
              <div>
                <dt>Phase</dt>
                <dd>{trace.phase ?? "—"}</dd>
              </div>
              <div>
                <dt>Turn</dt>
                <dd>{trace.player_turn ?? "—"}</dd>
              </div>
              <div>
                <dt>Model</dt>
                <dd>{trace.model ?? "—"}</dd>
              </div>
              <div>
                <dt>Temperature</dt>
                <dd>{trace.temperature ?? "—"}</dd>
              </div>
            </dl>

            <nav className="prompt-trace-modal__tabs" aria-label="Prompt 分区">
              {(["system", "user", "tools"] as const).map((id) => (
                <button
                  key={id}
                  type="button"
                  className={tab === id ? "is-active" : undefined}
                  onClick={() => setTab(id)}
                >
                  {id === "system" ? "System" : id === "user" ? "User" : "Tools"}
                </button>
              ))}
            </nav>

            <div className="prompt-trace-modal__body">
              {tab === "system" ? (
                <pre className="prompt-trace-modal__text">{trace.system_prompt}</pre>
              ) : null}
              {tab === "user" ? (
                <pre className="prompt-trace-modal__text">{trace.user_prompt}</pre>
              ) : null}
              {tab === "tools" ? (
                <pre className="prompt-trace-modal__text">
                  {JSON.stringify(trace.tool_calls ?? [], null, 2)}
                </pre>
              ) : null}
              {trace.assistant_content ? (
                <details className="prompt-trace-modal__assistant">
                  <summary>Assistant 文本</summary>
                  <pre className="prompt-trace-modal__text">{trace.assistant_content}</pre>
                </details>
              ) : null}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

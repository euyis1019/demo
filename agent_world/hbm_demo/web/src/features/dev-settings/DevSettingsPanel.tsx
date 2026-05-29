import { useState } from "react";
import {
  DEV_AGENT_PROMPTS,
  DEV_ENDINGS,
  DEV_PHASES,
  DEV_STORY,
} from "./devSettingsData";

export interface DevSettingsPanelProps {
  triggerClassName?: string;
}

export function DevSettingsPanel({ triggerClassName }: DevSettingsPanelProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="dev-settings">
      <button
        type="button"
        className={["dev-settings__toggle", triggerClassName ?? ""]
          .filter(Boolean)
          .join(" ")}
        onClick={() => setOpen((value) => !value)}
      >
        设定
      </button>
      {open ? (
        <section className="dev-settings__panel" aria-label="开发者设定">
          <header className="dev-settings__header">
            <div>
              <h2>{DEV_STORY.title}</h2>
              <p>{DEV_STORY.summary}</p>
            </div>
            <button type="button" onClick={() => setOpen(false)}>
              关闭
            </button>
          </header>

          <div className="dev-settings__grid">
            <section>
              <h3>章节</h3>
              {DEV_PHASES.map((phase) => (
                <article key={phase.id} className="dev-settings__item">
                  <strong>{phase.id} · {phase.title}</strong>
                  <p>{phase.rule}</p>
                </article>
              ))}
            </section>

            <section>
              <h3>结局判断</h3>
              {DEV_ENDINGS.map((ending) => (
                <article key={ending.id} className="dev-settings__item">
                  <strong>{ending.title}</strong>
                  <code>{ending.id}</code>
                  <p>{ending.rule}</p>
                </article>
              ))}
            </section>

            <section className="dev-settings__agents">
              <h3>角色 Prompt</h3>
              {DEV_AGENT_PROMPTS.map((agent) => (
                <article key={agent.id} className="dev-settings__item">
                  <strong>Agent {agent.id} · {agent.name}</strong>
                  <p>{agent.prompt}</p>
                </article>
              ))}
            </section>
          </div>
        </section>
      ) : null}
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import type { Stats, WorldLoopState } from "../../api/types";
import { DevSettingsPanel } from "../dev-settings";

export interface StatusPanelProps {
  stats: Stats;
  phase: string;
  playerTurn: number;
  maxTurns?: number;
  placeLabel: string;
  presentAgents?: string[];
  worldTick?: number;
  worldLoopState?: WorldLoopState;
  onPauseWorld?: () => void;
  onResumeWorld?: () => void;
  pauseDisabled?: boolean;
  onReset?: () => void;
  resetDisabled?: boolean;
  onSwitchToStoryMode?: () => void;
}

const STAT_ROWS: { key: keyof Stats; label: string }[] = [
  { key: "vision", label: "脑洞值" },
  { key: "execution", label: "逃避值" },
  { key: "trust", label: "记忆锚点" },
  { key: "burnout", label: "社死压力" },
];

/** F2-2 + F4-5 — Stats 变化高亮动画；Turn x / 25。F13 — pause/resume world loop。 */
export function StatusPanel({
  stats,
  phase,
  playerTurn,
  maxTurns = 25,
  placeLabel,
  presentAgents = [],
  worldTick,
  worldLoopState = "unknown",
  onPauseWorld,
  onResumeWorld,
  pauseDisabled = false,
  onReset,
  resetDisabled = false,
  onSwitchToStoryMode,
}: StatusPanelProps) {
  const prevStatsRef = useRef(stats);
  const [pulseKeys, setPulseKeys] = useState<Set<keyof Stats>>(new Set());
  const isPaused = worldLoopState === "paused";
  const showPauseControl = Boolean(onPauseWorld && onResumeWorld);

  useEffect(() => {
    const changed = new Set<keyof Stats>();
    for (const { key } of STAT_ROWS) {
      if (prevStatsRef.current[key] !== stats[key]) {
        changed.add(key);
      }
    }
    if (changed.size > 0) {
      setPulseKeys(changed);
      const timer = setTimeout(() => setPulseKeys(new Set()), 700);
      prevStatsRef.current = stats;
      return () => clearTimeout(timer);
    }
    prevStatsRef.current = stats;
    return undefined;
  }, [stats]);

  return (
    <>
      <div className="panel__header">Status</div>
      <div className="status-panel__wrap">
        <div className="panel__body status-panel">
          <section className="status-panel__section">
          <h2 className="status-panel__title">核心数值</h2>
          <ul className="stat-list">
            {STAT_ROWS.map(({ key, label }) => (
              <li key={key} className="stat-list__item">
                <span className="stat-list__label">{label}</span>
                <span
                  className={[
                    "stat-list__value",
                    pulseKeys.has(key) ? "stat-list__value--pulse" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                >
                  {stats[key]}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="status-panel__section">
          <h2 className="status-panel__title">进度</h2>
          <dl className="meta-list">
            <div className="meta-list__row">
              <dt>Phase</dt>
              <dd>{phase}</dd>
            </div>
            <div className="meta-list__row">
              <dt>Turn</dt>
              <dd className="meta-list__turn">
                <span className="meta-list__turn-current">{playerTurn}</span>
                <span className="meta-list__turn-sep">/</span>
                <span className="meta-list__turn-max">{maxTurns}</span>
              </dd>
            </div>
          </dl>
        </section>

        <section className="status-panel__section">
          <h2 className="status-panel__title">当前地点</h2>
          <p className="status-panel__place">{placeLabel}</p>
          {typeof worldTick === "number" ? (
            <p
              className={[
                "status-panel__tick",
                isPaused ? "status-panel__tick--paused" : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              World tick: {worldTick}
              {isPaused ? (
                <span className="status-panel__paused-tag"> (已暂停)</span>
              ) : null}
            </p>
          ) : null}
          {presentAgents.length > 0 ? (
            <ul className="presence-list">
              {presentAgents.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          ) : null}
        </section>
        </div>
        {showPauseControl || onReset || onSwitchToStoryMode ? (
          <div className="status-panel__footer">
            <DevSettingsPanel triggerClassName="status-panel__mode-btn" />
            {onSwitchToStoryMode ? (
              <button
                type="button"
                className="status-panel__mode-btn"
                onClick={onSwitchToStoryMode}
              >
                剧情模式
              </button>
            ) : null}
            {showPauseControl ? (
              <button
                type="button"
                className={[
                  "status-panel__pause-btn",
                  isPaused ? "status-panel__pause-btn--paused" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={() => {
                  if (isPaused) {
                    onResumeWorld?.();
                  } else {
                    onPauseWorld?.();
                  }
                }}
                disabled={pauseDisabled}
              >
                {isPaused ? "继续世界" : "暂停世界"}
              </button>
            ) : null}
            {onReset ? (
              <button
                type="button"
                className="status-panel__reset-btn"
                onClick={onReset}
                disabled={resetDisabled}
              >
                重开
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </>
  );
}

import { useEffect, useRef, useState } from "react";
import type { StatDimension, Stats, WorldLoopState } from "../../api/types";

export interface StatusPanelProps {
  stats: Stats;
  /** 属性维度定义（数据驱动：来自活跃 Story Pack 的 meta.stats）。 */
  dimensions?: StatDimension[];
  playerTurn: number;
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

/** F2-2 + F4-5 — Stats 变化高亮动画。F13 — pause/resume world loop。维度集数据驱动。 */
export function StatusPanel({
  stats,
  dimensions = [],
  playerTurn,
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
  const [pulseKeys, setPulseKeys] = useState<Set<string>>(new Set());
  // 维度由活跃 Story Pack 的 meta.stats 决定；故事未定义属性面板就不显示。
  const statsUsed = dimensions.length > 0;
  const isPaused = worldLoopState === "paused";
  const showPauseControl = Boolean(onPauseWorld && onResumeWorld);

  useEffect(() => {
    const changed = new Set<string>();
    for (const key of Object.keys(stats)) {
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
          {statsUsed ? (
            <section className="status-panel__section">
              <h2 className="status-panel__title">核心数值</h2>
              <ul className="stat-list">
                {dimensions.map(({ key, label }) => (
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
                      {stats[key] ?? 0}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

        <section className="status-panel__section">
          <h2 className="status-panel__title">进度</h2>
          <dl className="meta-list">
            <div className="meta-list__row">
              <dt>回合</dt>
              <dd className="meta-list__turn">
                <span className="meta-list__turn-current">{playerTurn}</span>
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

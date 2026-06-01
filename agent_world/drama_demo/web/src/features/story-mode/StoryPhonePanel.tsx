import { useState } from "react";
import type { StatDimension, Stats } from "../../api/types";

export interface StoryPhonePanelProps {
  /** 当前任务标题。 */
  phase?: string;
  /** 当前地点显示名。 */
  placeLabel?: string;
  /** 在场 NPC 名字。 */
  presentAgents?: string[];
  /** 世界 tick。 */
  worldTick?: number;
  /** 玩家回合。 */
  playerTurn?: number;
  stats?: Stats;
  dimensions?: StatDimension[];
  tension?: number;
}

/**
 * #4：玩家的「上帝模式手机」——默认收起一个 📱 按钮，点开是一块信息面板，集中看当前任务/所在地/在场人物/
 * 回合·时间/各项数值。把原本散在动作条里的东西收成一个随手可查的「手机」。
 */
export function StoryPhonePanel({
  phase,
  placeLabel,
  presentAgents = [],
  worldTick,
  playerTurn,
  stats,
  dimensions = [],
  tension,
}: StoryPhonePanelProps) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`story-phone ${open ? "is-open" : ""}`}>
      <button
        type="button"
        className="story-phone__toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        📱 {open ? "收起" : "信息"}
      </button>
      {open ? (
        <div className="story-phone__panel">
          <div className="story-phone__row">
            <span>当前任务</span>
            <b>{phase || "—"}</b>
          </div>
          <div className="story-phone__row">
            <span>所在地</span>
            <b>{placeLabel || "—"}</b>
          </div>
          <div className="story-phone__row">
            <span>在场</span>
            <b>{presentAgents.length ? presentAgents.join("、") : "暂无别人"}</b>
          </div>
          <div className="story-phone__row">
            <span>进度</span>
            <b>
              第 {playerTurn ?? 1} 回合{worldTick != null ? ` · t=${worldTick}` : ""}
            </b>
          </div>
          {(tension != null || dimensions.length) ? (
            <div className="story-phone__stats">
              {tension != null ? (
                <span className="story-phone__stat">张力 {Math.max(0, Math.min(100, Math.round(tension)))}</span>
              ) : null}
              {dimensions.map((d) => (
                <span key={d.key} className="story-phone__stat">
                  {d.label} {stats?.[d.key] ?? 0}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

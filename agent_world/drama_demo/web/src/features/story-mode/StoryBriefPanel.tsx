import { useState } from "react";
import type { Onboarding } from "../../api/types";

export interface StoryBriefPanelProps {
  /** 管理 agent 生成的开场引导：背景 + 此刻能做什么。删「任务/幕」后用它给玩家「情境/线索」指引。 */
  onboarding?: Onboarding | null;
  /** 当前「线索」：随玩家触发 bert 自动更新的下一步指引（优先于静态开场钩子）。 */
  clues?: string[];
}

/**
 * 📖 剧情——随手可重看的「我现在在哪个局里、能做什么」。开场弹窗看过就消失，玩家容易迷茫；
 * 这个折叠面板把 onboarding（背景 + 提示）+ 随进度更新的「当前线索」常驻一个角标，点开即可回看，
 * 补上删幕后的目标感空洞。
 */
export function StoryBriefPanel({ onboarding, clues }: StoryBriefPanelProps) {
  const [open, setOpen] = useState(false);
  const activeClues = (clues ?? []).filter(Boolean);
  const hasBrief =
    !!onboarding &&
    (!!onboarding.background || !!onboarding.tips?.length || !!onboarding.hook);
  if (!hasBrief && !activeClues.length) {
    return null;
  }
  return (
    <div className={`story-corner-item story-brief ${open ? "is-open" : ""}`}>
      <button
        type="button"
        className="story-corner-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        📖 剧情
      </button>
      {open ? (
        <div className="story-corner-panel story-brief__panel">
          {onboarding?.title ? <p className="story-brief__title">{onboarding.title}</p> : null}
          {activeClues.length ? (
            <div className="story-brief__hook">
              <span className="story-brief__hook-mark" aria-hidden="true">🔍 当前线索</span>
              <ul className="story-brief__clues">
                {activeClues.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          ) : onboarding?.hook ? (
            <p className="story-brief__hook">
              <span className="story-brief__hook-mark" aria-hidden="true">🔍 线索</span>
              {onboarding.hook}
            </p>
          ) : null}
          {onboarding?.background ? (
            <p className="story-brief__background">{onboarding.background}</p>
          ) : null}
          {onboarding?.tips?.length ? (
            <ul className="story-brief__tips">
              {onboarding.tips.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

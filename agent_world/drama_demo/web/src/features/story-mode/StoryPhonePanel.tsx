import { useState } from "react";

export interface StoryPhonePanelProps {
  /** 当前地点显示名。 */
  placeLabel?: string;
  /** 世界 tick。 */
  worldTick?: number;
  /** 玩家回合。 */
  playerTurn?: number;
}

/**
 * #4：玩家的「上帝模式手机」——默认收起一个 📱 按钮，点开看所在地 + 回合·时间。
 * 在场人物由舞台上的立绘名册呈现、各项数值由左侧 HUD 常驻呈现，故此面板不再重复它们，只放「别处看不到」的进度信息。
 */
export function StoryPhonePanel({
  placeLabel,
  worldTick,
  playerTurn,
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
            <span>所在地</span>
            <b>{placeLabel || "—"}</b>
          </div>
          <div className="story-phone__row">
            <span>进度</span>
            <b>
              第 {playerTurn ?? 1} 回合{worldTick != null ? ` · t=${worldTick}` : ""}
            </b>
          </div>
        </div>
      ) : null}
    </div>
  );
}

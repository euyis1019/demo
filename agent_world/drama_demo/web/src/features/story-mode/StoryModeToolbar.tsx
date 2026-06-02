import type { ReactNode } from "react";
import type { WorldLoopState } from "../../api/types";

export interface StoryModeToolbarProps {
  viewMode: "god" | "story";
  worldLoopState?: WorldLoopState;
  pauseDisabled?: boolean;
  resetDisabled?: boolean;
  onToggleViewMode: () => void;
  onPauseWorld?: () => void;
  onResumeWorld?: () => void;
  onReset?: () => void;
  /** God mode only shows mode switch; story mode shows all controls. */
  compact?: boolean;
  /** 玩家工具（私信/剧情/收件箱）作为同排按钮接在控制键之后。 */
  actions?: ReactNode;
}

export function StoryModeToolbar({
  viewMode,
  worldLoopState = "unknown",
  pauseDisabled = false,
  resetDisabled = false,
  onToggleViewMode,
  onPauseWorld,
  onResumeWorld,
  onReset,
  compact = false,
  actions,
}: StoryModeToolbarProps) {
  const isPaused = worldLoopState === "paused";
  const showWorldControls = !compact && viewMode === "story";

  return (
    <div className="story-toolbar" role="toolbar" aria-label="剧情模式控制">
      <button
        type="button"
        className="story-toolbar__btn"
        onClick={onToggleViewMode}
      >
        {viewMode === "story" ? "上帝模式" : "剧情模式"}
      </button>
      {showWorldControls && onPauseWorld && onResumeWorld ? (
        <button
          type="button"
          className={[
            "story-toolbar__btn",
            isPaused ? "story-toolbar__btn--paused" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          onClick={() => {
            if (isPaused) {
              onResumeWorld();
            } else {
              onPauseWorld();
            }
          }}
          disabled={pauseDisabled}
        >
          {isPaused ? "继续世界" : "暂停世界"}
        </button>
      ) : null}
      {showWorldControls && onReset ? (
        <button
          type="button"
          className="story-toolbar__btn story-toolbar__btn--danger"
          onClick={onReset}
          disabled={resetDisabled}
        >
          重开
        </button>
      ) : null}
      {actions}
    </div>
  );
}

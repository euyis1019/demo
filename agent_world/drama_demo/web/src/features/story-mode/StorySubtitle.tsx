import type { KeyboardEvent } from "react";
import { PLAYER_AGENT_ID } from "../../constants/agents";
import { ChromaKeyAvatar } from "./ChromaKeyAvatar";
import type { StoryDialogueLine } from "./useStoryDialogue";

export interface StorySubtitleProps {
  line: StoryDialogueLine | null;
  placeholder?: string;
  /** Unread lines after the current one (same-tick burst). */
  remaining?: number;
  /** Whether clicking the strip steps to the next line. */
  hasNext?: boolean;
  /** Step to the next line in this tick's queue. */
  onAdvance?: () => void;
}

/** Bottom ADV strip — agent avatar left, player avatar right, centered dialogue.
 *  Click (when hasNext) to step through other agents' lines in the same tick. */
export function StorySubtitle({
  line,
  placeholder = "……",
  remaining = 0,
  hasNext = false,
  onAdvance,
}: StorySubtitleProps) {
  const isPlayer = line?.speakerId === PLAYER_AGENT_ID;
  const clickable = hasNext && Boolean(onAdvance);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!clickable) {
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onAdvance?.();
    }
  };

  return (
    <footer className="story-subtitle" aria-live="polite">
      <div
        className={[
          "story-subtitle__inner",
          line
            ? isPlayer
              ? "story-subtitle__inner--player"
              : "story-subtitle__inner--agent"
            : "story-subtitle__inner--empty",
          clickable ? "story-subtitle__inner--clickable" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={clickable ? () => onAdvance?.() : undefined}
        onKeyDown={handleKeyDown}
        role={clickable ? "button" : undefined}
        tabIndex={clickable ? 0 : undefined}
        aria-label={clickable ? `查看下一条发言，还有 ${remaining} 条` : undefined}
      >
        {line ? (
          <>
            <div className="story-subtitle__slot story-subtitle__slot--left">
              {!isPlayer ? (
                <ChromaKeyAvatar
                  src={line.avatarUrl}
                  fallbackSrc={line.avatarFallbackUrl}
                  className="story-subtitle__avatar"
                />
              ) : null}
            </div>
            <div className="story-subtitle__text-block">
              <p className="story-subtitle__name">{line.speakerName}</p>
              <p className="story-subtitle__content">{line.message.content}</p>
              {hasNext ? (
                <span className="story-subtitle__next-hint">
                  ▼ 还有 {remaining} 条发言 · 点击查看
                </span>
              ) : null}
            </div>
            <div className="story-subtitle__slot story-subtitle__slot--right">
              {isPlayer ? (
                <ChromaKeyAvatar
                  src={line.avatarUrl}
                  fallbackSrc={line.avatarFallbackUrl}
                  className="story-subtitle__avatar"
                />
              ) : null}
            </div>
          </>
        ) : (
          <p className="story-subtitle__placeholder">{placeholder}</p>
        )}
      </div>
    </footer>
  );
}

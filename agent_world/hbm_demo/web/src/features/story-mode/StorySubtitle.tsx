import { PLAYER_AGENT_ID } from "../../constants/agents";
import { ChromaKeyAvatar } from "./ChromaKeyAvatar";
import type { StoryDialogueLine } from "./useStoryDialogue";

export interface StorySubtitleProps {
  line: StoryDialogueLine | null;
  placeholder?: string;
}

/** Bottom ADV strip — agent avatar left, player avatar right, centered dialogue. */
export function StorySubtitle({
  line,
  placeholder = "……",
}: StorySubtitleProps) {
  const isPlayer = line?.speakerId === PLAYER_AGENT_ID;

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
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {line ? (
          <>
            <div className="story-subtitle__slot story-subtitle__slot--left">
              {!isPlayer ? (
                <ChromaKeyAvatar
                  src={line.avatarUrl}
                  className="story-subtitle__avatar"
                />
              ) : null}
            </div>
            <div className="story-subtitle__text-block">
              <p className="story-subtitle__name">{line.speakerName}</p>
              <p className="story-subtitle__content">{line.message.content}</p>
            </div>
            <div className="story-subtitle__slot story-subtitle__slot--right">
              {isPlayer ? (
                <ChromaKeyAvatar
                  src={line.avatarUrl}
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

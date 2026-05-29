import { PLAYER_AGENT_ID } from "../../constants/agents";
import type { StoryDialogueLine } from "./useStoryDialogue";

export interface StorySubtitleProps {
  line: StoryDialogueLine | null;
  placeholder?: string;
  pendingCount?: number;
  onAdvance?: () => void;
}

/** Bottom ADV strip with large galgame-style portrait and click-to-advance queue. */
export function StorySubtitle({
  line,
  placeholder = "……",
  pendingCount = 0,
  onAdvance,
}: StorySubtitleProps) {
  const isPlayer = line?.speakerId === PLAYER_AGENT_ID;
  const hasNext = pendingCount > 0;

  return (
    <footer
      className={[
        "story-subtitle",
        hasNext ? "story-subtitle--has-next" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-live="polite"
      onClick={() => {
        if (hasNext) {
          onAdvance?.();
        }
      }}
    >
      {line ? (
        <img
          src={line.portraitUrl}
          className={[
            "story-portrait",
            isPlayer ? "story-portrait--player" : "story-portrait--agent",
            `story-portrait--pose-${line.pose}`,
          ].join(" ")}
          alt={line.speakerName}
        />
      ) : null}
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
            <div className="story-subtitle__text-block">
              <p className="story-subtitle__name">{line.speakerName}</p>
              <p className="story-subtitle__content">{line.message.content}</p>
              {hasNext ? (
                <p className="story-subtitle__next">
                  点击查看下一条 · {pendingCount}
                </p>
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

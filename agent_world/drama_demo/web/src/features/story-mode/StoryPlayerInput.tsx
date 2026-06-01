import { useCallback, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

export interface StoryPlayerInputProps {
  onSend?: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

const MAX_FIELD_HEIGHT_PX = 160;

function resizeField(field: HTMLTextAreaElement | null) {
  if (!field) {
    return;
  }
  field.style.height = "auto";
  const next = Math.min(field.scrollHeight, MAX_FIELD_HEIGHT_PX);
  field.style.height = `${next}px`;
  field.style.overflowY =
    field.scrollHeight > MAX_FIELD_HEIGHT_PX ? "auto" : "hidden";
}

/** Top-centered pill input — single line by default, grows with wrapped text. */
export function StoryPlayerInput({
  onSend,
  disabled = false,
  placeholder = "输入你的台词…",
}: StoryPlayerInputProps) {
  const [text, setText] = useState("");
  const fieldRef = useRef<HTMLTextAreaElement>(null);

  const handleChange = useCallback((value: string) => {
    setText(value);
    resizeField(fieldRef.current);
  }, []);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    submitText();
  }

  function submitText() {
    const trimmed = text.trim();
    if (!trimmed || disabled) {
      return;
    }
    onSend?.(trimmed);
    setText("");
    requestAnimationFrame(() => resizeField(fieldRef.current));
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) {
      return;
    }
    event.preventDefault();
    submitText();
  }

  return (
    <form className="story-player-input" onSubmit={handleSubmit}>
      <textarea
        ref={fieldRef}
        className="story-player-input__field"
        value={text}
        onChange={(event) => handleChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        rows={1}
        aria-label="玩家台词"
      />
    </form>
  );
}

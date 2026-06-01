import { useState, type FormEvent } from "react";

export interface PlayerInputProps {
  onSend?: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

/** F2-3 — 玩家输入框（F2 静态；F3 接 sendTurn）。 */
export function PlayerInput({
  onSend,
  disabled = false,
  placeholder = "输入你的台词…",
}: PlayerInputProps) {
  const [text, setText] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) {
      return;
    }
    onSend?.(trimmed);
    setText("");
  }

  return (
    <form className="player-input" onSubmit={handleSubmit}>
      <textarea
        className="player-input__field"
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        rows={3}
        aria-label="玩家台词"
      />
      <button
        type="submit"
        className="player-input__submit"
        disabled={disabled || text.trim().length === 0}
      >
        发送
      </button>
    </form>
  );
}

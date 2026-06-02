import { useCallback, useEffect, useState } from "react";
import { getJoinableGroups, postPlayerAction } from "../../api/drama";
import { PLAYER_AGENT_ID, VIRTUAL_PLAYER_AGENT_ID } from "../../constants/agents";

export interface StoryComposeBarProps {
  /** agent id → 名称（私信目标）。 */
  nameMap: Record<string, string>;
  /** 外部（在场名册点击）预选的私信对象 id；变化时展开并选中。 */
  presetTarget?: string | null;
  /** 预选消费后回调，清掉外部选择。 */
  onTargetConsumed?: () => void;
  disabled?: boolean;
}

/**
 * 💬 私信/群聊**发送**——角标折叠面板（不再常驻顶部、不用原生 select/蓝按钮，改玻璃 + 人物筹码，保沉浸）。
 * 私信(rdc)：选一个 NPC 筹码 + 打字发送；群聊(grp)：选一个可加入的群 + 发送（群受后端门控）。
 * 在场名册点某个 NPC 会自动展开并选中他。
 */
export function StoryComposeBar({ nameMap, presetTarget, onTargetConsumed, disabled }: StoryComposeBarProps) {
  const agentOptions = Object.keys(nameMap)
    .filter((id) => id !== PLAYER_AGENT_ID && id !== VIRTUAL_PLAYER_AGENT_ID)
    .sort((a, b) => {
      const na = Number(a);
      const nb = Number(b);
      if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
      return a.localeCompare(b);
    });

  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"rdc" | "grp">("rdc");
  const [rdcTarget, setRdcTarget] = useState<string>(agentOptions[0] ?? "");
  const [groupId, setGroupId] = useState<string>("");
  const [joinable, setJoinable] = useState<number[] | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const refreshJoinable = useCallback(async () => {
    try {
      const res = await getJoinableGroups();
      if (res.success && res.data) {
        setJoinable(res.data.gate_enabled ? res.data.groups.map((g) => g.group_id) : null);
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void refreshJoinable();
  }, [refreshJoinable]);

  // 在场名册点了某个 NPC → 展开 + 切私信 + 选中他
  useEffect(() => {
    if (presetTarget) {
      setOpen(true);
      setMode("rdc");
      setRdcTarget(String(presetTarget));
      onTargetConsumed?.();
    }
  }, [presetTarget, onTargetConsumed]);

  const off = disabled || busy;

  async function send() {
    const content = text.trim();
    if (off || !content) return;
    if (mode === "rdc" && !rdcTarget) {
      setStatus("先选一个私信对象");
      return;
    }
    if (mode === "grp" && !groupId) {
      setStatus("先选一个群");
      return;
    }
    setBusy(true);
    setStatus(null);
    try {
      const req =
        mode === "rdc"
          ? { action: "rdc" as const, target_id: Number(rdcTarget), content }
          : { action: "grp" as const, group_id: Number(groupId), content };
      const res = await postPlayerAction(req);
      if (res.success && res.data?.accepted) {
        setStatus(mode === "rdc" ? "✓ 私信已发出" : "✓ 群消息已发出");
        setText("");
      } else {
        setStatus(`✗ ${res.data?.hint ?? res.data?.reason ?? res.error ?? "被拒绝"}`);
      }
    } catch {
      setStatus("✗ 发送出错");
    } finally {
      setBusy(false);
      void refreshJoinable();
    }
  }

  return (
    <div className={`story-corner-item story-compose ${open ? "is-open" : ""}`}>
      <button
        type="button"
        className="story-corner-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        💬 私信
      </button>
      {open ? (
        <div className="story-corner-panel story-compose__panel">
          <div className="story-compose__tabs">
            <button type="button" className={mode === "rdc" ? "is-active" : ""} onClick={() => setMode("rdc")}>
              私信
            </button>
            <button type="button" className={mode === "grp" ? "is-active" : ""} onClick={() => setMode("grp")}>
              群聊
            </button>
          </div>

          {mode === "rdc" ? (
            <div className="story-compose__targets" role="radiogroup" aria-label="私信对象">
              {agentOptions.length ? (
                agentOptions.map((id) => (
                  <button
                    key={id}
                    type="button"
                    role="radio"
                    aria-checked={rdcTarget === id}
                    className={`story-compose__chip ${rdcTarget === id ? "is-on" : ""}`}
                    onClick={() => setRdcTarget(id)}
                    disabled={off}
                  >
                    {nameMap[id] ?? id}
                  </button>
                ))
              ) : (
                <span className="story-compose__hint">暂无可私信的人</span>
              )}
            </div>
          ) : joinable !== null ? (
            <div className="story-compose__targets" role="radiogroup" aria-label="群">
              {joinable.length ? (
                joinable.map((g) => (
                  <button
                    key={g}
                    type="button"
                    role="radio"
                    aria-checked={groupId === String(g)}
                    className={`story-compose__chip ${groupId === String(g) ? "is-on" : ""}`}
                    onClick={() => setGroupId(String(g))}
                    disabled={off}
                  >
                    群 {g}
                  </button>
                ))
              ) : (
                <span className="story-compose__hint">暂无可加群（先当面取得同意）</span>
              )}
            </div>
          ) : (
            <input
              className="story-compose__group"
              inputMode="numeric"
              value={groupId}
              placeholder="群号"
              onChange={(e) => setGroupId(e.target.value.replace(/\D/g, ""))}
              disabled={off}
            />
          )}

          <div className="story-compose__row">
            <input
              className="story-compose__text"
              value={text}
              placeholder={mode === "rdc" ? "悄悄对他说…" : "群里说…"}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.nativeEvent.isComposing) void send();
              }}
              disabled={off}
            />
            <button
              type="button"
              className="story-compose__send"
              disabled={off || !text.trim()}
              onClick={() => void send()}
            >
              发送
            </button>
          </div>
          {status ? <div className="story-compose__status">{status}</div> : null}
        </div>
      ) : null}
    </div>
  );
}

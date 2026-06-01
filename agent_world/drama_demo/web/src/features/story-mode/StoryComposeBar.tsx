import { useCallback, useEffect, useState } from "react";
import { getJoinableGroups, postPlayerAction } from "../../api/drama";
import { PLAYER_AGENT_ID, VIRTUAL_PLAYER_AGENT_ID } from "../../constants/agents";

export interface StoryComposeBarProps {
  /** agent id → 名称（私信目标下拉）。 */
  nameMap: Record<string, string>;
  /** 外部（在场名册点击）预选的私信对象 id；变化时切到私信并选中。 */
  presetTarget?: string | null;
  /** 预选消费后回调，清掉外部选择。 */
  onTargetConsumed?: () => void;
  disabled?: boolean;
}

/**
 * #4：私信/群聊**发送**栏——放在收件箱对话框下面的输入框。
 * 私信(rdc)：选一个 NPC + 打字发送；群聊(grp)：选一个可加入的群 + 发送（群受后端门控）。
 * 点左侧/在场名册里的 NPC 会自动切到私信并选中他。
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

  // 在场名册点了某个 NPC → 切私信并选中他
  useEffect(() => {
    if (presetTarget) {
      setMode("rdc");
      setRdcTarget(String(presetTarget));
      onTargetConsumed?.();
    }
  }, [presetTarget, onTargetConsumed]);

  const off = disabled || busy;

  async function send() {
    const content = text.trim();
    if (off || !content) return;
    setBusy(true);
    setStatus(null);
    try {
      const req =
        mode === "rdc"
          ? { action: "rdc" as const, target_id: Number(rdcTarget), content }
          : { action: "grp" as const, group_id: Number(groupId), content };
      if (mode === "rdc" && !rdcTarget) {
        setStatus("先选一个私信对象");
        return;
      }
      if (mode === "grp" && !groupId) {
        setStatus("先选一个群");
        return;
      }
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
    <div className="story-compose">
      <div className="story-compose__tabs">
        <button type="button" className={mode === "rdc" ? "is-active" : ""} onClick={() => setMode("rdc")}>
          私信
        </button>
        <button type="button" className={mode === "grp" ? "is-active" : ""} onClick={() => setMode("grp")}>
          群聊
        </button>
        {mode === "rdc" ? (
          <select value={rdcTarget} onChange={(e) => setRdcTarget(e.target.value)} disabled={off}>
            {agentOptions.map((id) => (
              <option key={id} value={id}>
                {nameMap[id] ?? id}
              </option>
            ))}
          </select>
        ) : joinable !== null ? (
          <select value={groupId} onChange={(e) => setGroupId(e.target.value)} disabled={off}>
            <option value="">{joinable.length ? "选择群…" : "暂无可加群(先 F2F 取得同意)"}</option>
            {joinable.map((g) => (
              <option key={g} value={String(g)}>
                群 {g}
              </option>
            ))}
          </select>
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
      </div>
      <div className="story-compose__row">
        <input
          className="story-compose__text"
          value={text}
          placeholder={mode === "rdc" ? "私信内容…" : "群聊内容…"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.nativeEvent.isComposing) void send();
          }}
          disabled={off}
        />
        <button type="button" disabled={off || !text.trim()} onClick={() => void send()}>
          发送
        </button>
      </div>
      {status ? <div className="story-compose__status">{status}</div> : null}
    </div>
  );
}

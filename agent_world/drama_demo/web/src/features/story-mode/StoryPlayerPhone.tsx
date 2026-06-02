import { useCallback, useEffect, useMemo, useState } from "react";
import type { GameMessage } from "../../api/types";
import type { AgentInbox } from "../../store/agentInbox";
import { rdcPeerId } from "../../store/agentInbox";
import { getJoinableGroups, postPlayerAction } from "../../api/drama";
import { PLAYER_AGENT_ID, VIRTUAL_PLAYER_AGENT_ID } from "../../constants/agents";
import { sortMessages } from "../../utils/messages";

export interface StoryPlayerPhoneProps {
  /** 玩家(agent 0)收件箱：私信(rdc) + 群聊(grp)。 */
  inbox?: AgentInbox;
  /** agent id → 名称（联系人名 + 私信对象）。 */
  nameMap: Record<string, string>;
  /** 在场名册点某个 NPC → 打开手机并直接进该联系人的私信对话。 */
  presetTarget?: string | null;
  onTargetConsumed?: () => void;
  /** 非游玩中/加载时禁用发送。 */
  disabled?: boolean;
}

type Selection =
  | { kind: "rdc"; peer: string }
  | { kind: "grp"; groupId: string }
  | null;

/**
 * 📱 玩家手机——把「私信发送」与「收件箱阅读」合进一个类上帝模式手机界面：
 * 联系人列表（每个 NPC 一行 + 群聊）→ 点进某人即是一条对话流（左 NPC / 右玩家），
 * 底部直接打字发送。取代原先分开的「💬 私信」发送栏 + 「📨 收件箱」折叠条。
 */
export function StoryPlayerPhone({
  inbox,
  nameMap,
  presetTarget,
  onTargetConsumed,
  disabled,
}: StoryPlayerPhoneProps) {
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState<Selection>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [joinable, setJoinable] = useState<number[] | null>(null);

  const rdc = useMemo(() => inbox?.rdc ?? [], [inbox?.rdc]);
  const grp = useMemo(() => inbox?.grp ?? [], [inbox?.grp]);

  const npcIds = useMemo(
    () =>
      Object.keys(nameMap)
        .filter((id) => id !== PLAYER_AGENT_ID && id !== VIRTUAL_PLAYER_AGENT_ID)
        .sort((a, b) => {
          const na = Number(a);
          const nb = Number(b);
          return Number.isNaN(na) || Number.isNaN(nb) ? a.localeCompare(b) : na - nb;
        }),
    [nameMap],
  );

  // 每个联系人最近一条私信（升序排序后后写覆盖即为最新）。
  const lastByPeer = useMemo(() => {
    const m: Record<string, GameMessage> = {};
    for (const msg of sortMessages(rdc)) {
      m[rdcPeerId(msg, PLAYER_AGENT_ID)] = msg;
    }
    return m;
  }, [rdc]);

  const groupIds = useMemo(() => {
    const ids = new Set<string>();
    for (const m of grp) if (m.group_id != null) ids.add(String(m.group_id));
    if (joinable) joinable.forEach((g) => ids.add(String(g)));
    return [...ids].sort((a, b) => Number(a) - Number(b));
  }, [grp, joinable]);

  const threadMessages = useMemo(() => {
    if (!sel) return [];
    if (sel.kind === "rdc") {
      return sortMessages(rdc.filter((m) => rdcPeerId(m, PLAYER_AGENT_ID) === sel.peer));
    }
    return sortMessages(grp.filter((m) => String(m.group_id ?? "") === sel.groupId));
  }, [sel, rdc, grp]);

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
    if (open) void refreshJoinable();
  }, [open, refreshJoinable]);

  // 在场名册点了某个 NPC → 打开手机并直接进该联系人私信。
  useEffect(() => {
    if (presetTarget) {
      setOpen(true);
      setSel({ kind: "rdc", peer: String(presetTarget) });
      setStatus(null);
      onTargetConsumed?.();
    }
  }, [presetTarget, onTargetConsumed]);

  const off = disabled || busy;

  async function send() {
    const content = text.trim();
    if (!sel || !content || off) return;
    setBusy(true);
    setStatus(null);
    try {
      const req =
        sel.kind === "rdc"
          ? { action: "rdc" as const, target_id: Number(sel.peer), content }
          : { action: "grp" as const, group_id: Number(sel.groupId), content };
      const res = await postPlayerAction(req);
      if (res.success && res.data?.accepted) {
        setText("");
        setStatus("✓ 已送出");
      } else {
        setStatus(`✗ ${res.data?.hint ?? res.data?.reason ?? res.error ?? "被拒绝"}`);
      }
    } catch {
      setStatus("✗ 发送出错");
    } finally {
      setBusy(false);
      if (sel?.kind === "grp") void refreshJoinable();
    }
  }

  const unread = rdc.length + grp.length;
  const headerTitle = !sel
    ? "消息"
    : sel.kind === "rdc"
      ? nameMap[sel.peer] ?? `Agent ${sel.peer}`
      : `群 ${sel.groupId}`;

  return (
    <div className="story-corner-item story-phone-launcher">
      <button
        type="button"
        className="story-corner-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        📱 消息{unread ? `（${unread}）` : ""}
      </button>
      {open ? (
        <div className="modal-backdrop modal-backdrop--world" role="presentation" onClick={() => setOpen(false)}>
          <div
            className="agent-phone-modal"
            role="dialog"
            aria-modal="true"
            aria-label="玩家消息"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="agent-phone-modal__header">
              <div>
                <h2>{headerTitle}</h2>
                <p className="agent-phone-modal__subtitle">
                  {sel ? (sel.kind === "rdc" ? "私信" : "群聊") : "私信 · 群聊"}
                </p>
              </div>
              {sel ? (
                <button
                  type="button"
                  className="modal-close"
                  onClick={() => {
                    setSel(null);
                    setStatus(null);
                  }}
                >
                  返回
                </button>
              ) : (
                <button type="button" className="modal-close" onClick={() => setOpen(false)}>
                  关闭
                </button>
              )}
            </header>

            <div className="agent-phone-modal__body">
              {sel ? (
                <div className="story-phone-thread">
                  <div className="story-phone-thread__scroll">
                    {threadMessages.length === 0 ? (
                      <p className="agent-phone__empty">还没有消息，写一句开始吧</p>
                    ) : (
                      threadMessages.map((m, i) => {
                        const mine = String(m.sender_id ?? "") === PLAYER_AGENT_ID;
                        return (
                          <div
                            key={`${m.attempted_at ?? 0}-${i}`}
                            className={`story-phone-bubble ${mine ? "is-mine" : "is-them"}`}
                          >
                            <span className="story-phone-bubble__text">{m.content}</span>
                          </div>
                        );
                      })
                    )}
                  </div>
                  <div className="story-phone-compose">
                    <input
                      className="story-phone-compose__text"
                      value={text}
                      placeholder={sel.kind === "rdc" ? "悄悄对他说…" : "群里说…"}
                      onChange={(e) => setText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.nativeEvent.isComposing) void send();
                      }}
                      disabled={off}
                    />
                    <button
                      type="button"
                      className="story-phone-compose__send"
                      disabled={off || !text.trim()}
                      onClick={() => void send()}
                    >
                      发送
                    </button>
                  </div>
                  {status ? <div className="story-phone-compose__status">{status}</div> : null}
                </div>
              ) : (
                <div className="agent-phone-modal__scroll">
                  {npcIds.length === 0 && groupIds.length === 0 ? (
                    <p className="agent-phone__empty">暂无可私信的人</p>
                  ) : (
                    <ul className="agent-contact-list">
                      {npcIds.map((id) => {
                        const last = lastByPeer[id];
                        return (
                          <li key={`rdc-${id}`}>
                            <button
                              type="button"
                              className="agent-contact-list__item"
                              onClick={() => setSel({ kind: "rdc", peer: id })}
                            >
                              <span className="agent-contact-list__avatar agent-contact-list__avatar--rdc" aria-hidden>
                                私
                              </span>
                              <span className="agent-contact-list__main">
                                <span className="agent-contact-list__title-row">
                                  <span className="agent-contact-list__title">{nameMap[id] ?? `Agent ${id}`}</span>
                                </span>
                                <span className="agent-contact-list__preview">
                                  {last ? last.content : "点此发起私信"}
                                </span>
                              </span>
                            </button>
                          </li>
                        );
                      })}
                      {groupIds.map((gid) => {
                        const last = sortMessages(grp.filter((m) => String(m.group_id ?? "") === gid)).at(-1);
                        return (
                          <li key={`grp-${gid}`}>
                            <button
                              type="button"
                              className="agent-contact-list__item"
                              onClick={() => setSel({ kind: "grp", groupId: gid })}
                            >
                              <span className="agent-contact-list__avatar agent-contact-list__avatar--grp" aria-hidden>
                                群
                              </span>
                              <span className="agent-contact-list__main">
                                <span className="agent-contact-list__title-row">
                                  <span className="agent-contact-list__title">群 {gid}</span>
                                </span>
                                <span className="agent-contact-list__preview">{last ? last.content : "群聊"}</span>
                              </span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

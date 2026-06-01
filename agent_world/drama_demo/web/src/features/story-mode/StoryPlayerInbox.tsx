import { useMemo, useState } from "react";
import type { GameMessage } from "../../api/types";
import type { AgentInbox } from "../../store/agentInbox";

export interface StoryPlayerInboxProps {
  /** 玩家(agent 0)的收件箱：私信(rdc) + 群聊(grp)。 */
  inbox?: AgentInbox;
  nameMap: Record<string, string>;
}

function nameOf(id: number | undefined, nameMap: Record<string, string>): string {
  if (id === 0) return "我";
  if (id == null) return "?";
  return nameMap[String(id)] ?? `Agent ${id}`;
}

function recent(list: GameMessage[], n = 20): GameMessage[] {
  return [...list]
    .sort((a, b) => (a.attempted_at ?? 0) - (b.attempted_at ?? 0))
    .slice(-n);
}

/**
 * 剧情模式玩家收件箱（体检 B3）：把发往玩家的私信/群聊接到 UI——
 * 玩家发完私信能看到对方回信、加群后能看到群里在聊什么。默认折叠，有未读时高亮。
 */
export function StoryPlayerInbox({ inbox, nameMap }: StoryPlayerInboxProps) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"rdc" | "grp">("rdc");

  const rdc = useMemo(() => recent(inbox?.rdc ?? []), [inbox?.rdc]);
  const grp = useMemo(() => recent(inbox?.grp ?? []), [inbox?.grp]);
  const total = rdc.length + grp.length;

  if (total === 0) {
    return null;
  }

  const list = tab === "rdc" ? rdc : grp;

  return (
    <div className={`story-inbox ${open ? "story-inbox--open" : ""}`}>
      <button type="button" className="story-inbox__toggle" onClick={() => setOpen((v) => !v)}>
        📨 收件箱（私信 {rdc.length} · 群聊 {grp.length}）{open ? "▾" : "▸"}
      </button>
      {open ? (
        <div className="story-inbox__panel">
          <div className="story-inbox__tabs">
            <button
              type="button"
              className={tab === "rdc" ? "is-active" : ""}
              onClick={() => setTab("rdc")}
            >
              私信
            </button>
            <button
              type="button"
              className={tab === "grp" ? "is-active" : ""}
              onClick={() => setTab("grp")}
            >
              群聊
            </button>
          </div>
          <ul className="story-inbox__list">
            {list.length === 0 ? (
              <li className="story-inbox__empty">暂无{tab === "rdc" ? "私信" : "群聊"}</li>
            ) : (
              list.map((m, i) => (
                <li key={`${m.attempted_at ?? 0}-${i}`} className="story-inbox__item">
                  <span className="story-inbox__from">
                    {tab === "grp" && m.group_id != null ? `[群${m.group_id}] ` : ""}
                    {nameOf(m.sender_id, nameMap)}
                    {tab === "rdc" && m.sender_id !== 0
                      ? " → 我"
                      : tab === "rdc"
                        ? ` → ${nameOf(m.recipient_id, nameMap)}`
                        : ""}
                    ：
                  </span>
                  <span className="story-inbox__content">{m.content}</span>
                </li>
              ))
            )}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

import { create } from "zustand";
import type { PlayerView } from "../net/protocol";

// 聊天日志累积：player_view 是每拍的增量，这里按 message_id 去重后累积成
// 本地(当面)/私聊(按 npc)/群聊(按 gid) 三类 log + 未读角标。复刻 phone_menu.gd。
export interface Line {
  who: string;        // 显示名（"我" 或对方名）
  text: string;
  kind: "me" | "them" | "overheard" | "failed";
}

interface ChatState {
  local: Line[];
  priv: Record<number, Line[]>;
  group: Record<number, Line[]>;
  unreadPriv: number;
  unreadGroup: number;
  seen: Record<string, boolean>;

  ingest: (pv: PlayerView, names: Record<number, string>, playerId: number) => void;
  pushMine: (channel: "local" | "priv" | "group", key: number, text: string) => void;
  clearUnread: (which: "priv" | "group") => void;
}

const cap = (s: string, n = 200) => (s.length > n ? s.slice(0, n) + "…" : s);

export const useChat = create<ChatState>((set, get) => ({
  local: [],
  priv: {},
  group: {},
  unreadPriv: 0,
  unreadGroup: 0,
  seen: {},

  ingest: (pv, names, _playerId) => {
    const st = get();
    const seen = { ...st.seen };
    const local = [...st.local];
    const priv: Record<number, Line[]> = { ...st.priv };
    const group: Record<number, Line[]> = { ...st.group };
    let uP = st.unreadPriv;
    let uG = st.unreadGroup;
    const nameOf = (id?: number) => (id == null ? "?" : names[id] ?? `agent_${id}`);
    const once = (k: string) => {
      if (seen[k]) return false;
      seen[k] = true;
      return true;
    };

    for (const m of pv.f2f ?? []) {
      if (once("d" + m.message_id)) local.push({ who: nameOf(m.sender_id), text: cap(m.content ?? ""), kind: "them" });
    }
    for (const m of pv.overheard ?? []) {
      if (seen["d" + m.message_id]) continue;
      if (once("o" + m.message_id)) local.push({ who: nameOf(m.sender_id), text: cap(m.content ?? ""), kind: "overheard" });
    }
    for (const m of pv.incoming ?? []) {
      if (once("d" + m.message_id)) {
        const sid = Number(m.sender_id);
        (priv[sid] ??= [...(st.priv[sid] ?? [])]).push({ who: nameOf(sid), text: cap(m.content ?? ""), kind: "them" });
        uP += 1;
      }
    }
    for (const m of pv.group ?? []) {
      if (once("g" + m.message_id)) {
        const gid = Number(m.group_id ?? 0);
        (group[gid] ??= [...(st.group[gid] ?? [])]).push({ who: nameOf(m.sender_id), text: cap(m.content ?? ""), kind: "them" });
        uG += 1;
      }
    }
    for (const m of pv.failed ?? []) {
      if (once("f" + m.message_id)) {
        const rid = Number(m.recipient_id);
        (priv[rid] ??= [...(st.priv[rid] ?? [])]).push({
          who: nameOf(rid), text: `（未送达：${m.reason ?? "不可达"}）`, kind: "failed",
        });
      }
    }
    set({ local, priv, group, unreadPriv: uP, unreadGroup: uG, seen });
  },

  pushMine: (channel, key, text) => {
    const st = get();
    const line: Line = { who: "我", text, kind: "me" };
    if (channel === "local") set({ local: [...st.local, line] });
    else if (channel === "priv") set({ priv: { ...st.priv, [key]: [...(st.priv[key] ?? []), line] } });
    else set({ group: { ...st.group, [key]: [...(st.group[key] ?? []), line] } });
  },

  clearUnread: (which) => set(which === "priv" ? { unreadPriv: 0 } : { unreadGroup: 0 }),
}));

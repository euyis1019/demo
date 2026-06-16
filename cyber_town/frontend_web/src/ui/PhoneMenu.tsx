import { useEffect, useRef, useState } from "react";
import { create } from "zustand";
import { useWorld } from "../store/worldStore";
import { useChat, type Line } from "../store/chatStore";
import { net } from "../net/ws";
import { setUiFocused } from "./uiState";
import { NPC_COLORS } from "../config";

type Tab = "local" | "priv" | "group";

interface UiStore {
  open: boolean;
  tab: Tab;
  activePriv: number;
  profile: number | null;
  setOpen: (o: boolean) => void;
  toggle: () => void;
  setTab: (t: Tab) => void;
  openPrivate: (id: number) => void;
  openProfile: (id: number) => void;
  closeProfile: () => void;
}
export const useUi = create<UiStore>((set) => ({
  open: false, tab: "local", activePriv: -1, profile: null,
  setOpen: (o) => { setUiFocused(o); set({ open: o }); },
  toggle: () => set((s) => { const o = !s.open; setUiFocused(o); return { open: o }; }),
  setTab: (t) => set({ tab: t }),
  openPrivate: (id) => { setUiFocused(true); set({ open: true, tab: "priv", activePriv: id }); },
  openProfile: (id) => { net.fetchTimeline(id); set({ profile: id }); },
  closeProfile: () => set({ profile: null }),
}));

// 找与玩家同地点的最近 NPC（E 直达私聊用）
function coLocatedNpc(): number {
  const s = useWorld.getState();
  const ploc = s.agents[String(s.playerId)]?.location;
  if (!ploc) return -1;
  for (const [k, v] of Object.entries(s.agents)) {
    const id = Number(k);
    if (id !== s.playerId && v.location === ploc) return id;
  }
  return -1;
}

export default function PhoneMenu() {
  const ui = useUi();
  const hello = useWorld((s) => s.hello);
  const agents = useWorld((s) => s.agents);
  const contacts = useWorld((s) => s.contacts);
  const playerId = useWorld((s) => s.playerId);

  // Tab/E/Esc 键
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code === "Tab") { e.preventDefault(); useUi.getState().toggle(); }
      else if (e.code === "Escape") { useUi.getState().closeProfile(); useUi.getState().setOpen(false); }
      else if (e.code === "KeyE") {
        const tgt = document.activeElement;
        if (tgt && (tgt.tagName === "INPUT" || tgt.tagName === "TEXTAREA")) return;
        if (!useUi.getState().open) {
          const id = coLocatedNpc();
          if (id >= 0) useUi.getState().openPrivate(id);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!ui.open) {
    return ui.profile != null ? <Profile id={ui.profile} names={names(hello)} /> : null;
  }

  const npcIds = hello ? Object.keys(hello.agents).map(Number).filter((i) => i !== playerId) : [];
  const groups = hello?.groups ?? [];

  return (
    <>
      <div style={panelStyle}>
        <div style={headerStyle}>
          <b>📱 小镇通</b>
          <span style={{ cursor: "pointer" }} onClick={() => ui.setOpen(false)}>✕</span>
        </div>
        <div style={tabsStyle}>
          <TabBtn cur={ui.tab} id="local" onClick={ui.setTab}>当面说</TabBtn>
          <TabBtn cur={ui.tab} id="priv" onClick={ui.setTab}>私聊</TabBtn>
          <TabBtn cur={ui.tab} id="group" onClick={ui.setTab}>群聊</TabBtn>
        </div>
        {ui.tab === "local" && <LocalTab />}
        {ui.tab === "priv" && (
          <PrivTab npcIds={npcIds} agents={agents} contacts={contacts}
            active={ui.activePriv} setActive={ui.openPrivate} openProfile={ui.openProfile} />
        )}
        {ui.tab === "group" && <GroupTab groups={groups} />}
      </div>
      {ui.profile != null && <Profile id={ui.profile} names={names(hello)} />}
    </>
  );
}

function names(hello: any): Record<number, string> {
  const m: Record<number, string> = {};
  if (hello) for (const [k, v] of Object.entries(hello.agents)) m[Number(k)] = v as string;
  return m;
}

function TabBtn({ cur, id, onClick, children }: { cur: Tab; id: Tab; onClick: (t: Tab) => void; children: any }) {
  return (
    <div onClick={() => onClick(id)} style={{
      flex: 1, textAlign: "center", padding: "6px 0", cursor: "pointer",
      background: cur === id ? "#3a4a63" : "transparent", borderRadius: 6, fontWeight: cur === id ? 700 : 400,
    }}>{children}</div>
  );
}

function Log({ lines }: { lines: Line[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, [lines.length]);
  return (
    <div ref={ref} style={logStyle}>
      {lines.length === 0 && <div style={{ opacity: 0.5 }}>（还没有消息）</div>}
      {lines.map((l, i) => (
        <div key={i} style={{ margin: "3px 0", color: l.kind === "failed" ? "#e88" : l.kind === "overheard" ? "#9ab" : "#eee" }}>
          <span style={{ color: l.who === "我" ? "#fc6" : "#8cf" }}>{l.who}</span>
          {l.kind === "overheard" ? "（旁听）" : ""}：{l.text}
        </div>
      ))}
    </div>
  );
}

function Input({ placeholder, onSend }: { placeholder: string; onSend: (t: string) => void }) {
  const [v, setV] = useState("");
  return (
    <div style={{ display: "flex", gap: 6, padding: 8 }}>
      <input
        value={v} placeholder={placeholder}
        onFocus={() => setUiFocused(true)} onBlur={() => setUiFocused(useUi.getState().open)}
        onChange={(e) => setV(e.target.value)}
        onKeyDown={(e) => { if (e.code === "Enter" && v.trim()) { onSend(v.trim()); setV(""); } }}
        style={inputStyle}
      />
      <button onClick={() => { if (v.trim()) { onSend(v.trim()); setV(""); } }} style={btnStyle}>发</button>
    </div>
  );
}

function LocalTab() {
  const local = useChat((s) => s.local);
  return (
    <>
      <Log lines={local} />
      <Input placeholder="对在场的人说…" onSend={(t) => { net.speakToLocal(t); useChat.getState().pushMine("local", 0, t); }} />
    </>
  );
}

function PrivTab({ npcIds, agents, contacts, active, setActive, openProfile }: any) {
  const priv = useChat((s) => s.priv);
  const aff = (id: number) => agents[String(id)]?.affinity_to_player;
  return (
    <div style={{ display: "flex", height: 300 }}>
      <div style={{ width: 92, borderRight: "1px solid #2c3a52", overflowY: "auto" }}>
        {npcIds.map((id: number) => {
          const c = contacts.find((x: any) => x.agent_id === id);
          const reach = c ? c.can_reach_now : true;
          return (
            <div key={id} onClick={() => setActive(id)} style={{
              padding: "6px 8px", cursor: "pointer", fontSize: 13,
              background: active === id ? "#3a4a63" : "transparent", opacity: reach ? 1 : 0.5,
            }}>
              <span style={{ color: NPC_COLORS[id] }}>●</span> {agents[String(id)]?.name ?? id}
              {aff(id) != null && <div style={{ fontSize: 11, color: "#e88" }}>♥{aff(id)}</div>}
            </div>
          );
        })}
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {active >= 0 ? (
          <>
            <div style={{ padding: "4px 8px", borderBottom: "1px solid #2c3a52", display: "flex", justifyContent: "space-between" }}>
              <b>与 {agents[String(active)]?.name ?? active}</b>
              <span style={{ cursor: "pointer", color: "#8cf" }} onClick={() => openProfile(active)}>看档案</span>
            </div>
            <Log lines={priv[active] ?? []} />
            <Input placeholder="发条私信…" onSend={(t) => { net.sendMessage(active, t); useChat.getState().pushMine("priv", active, t); }} />
          </>
        ) : <div style={{ padding: 16, opacity: 0.6 }}>← 选一个村民私聊</div>}
      </div>
    </div>
  );
}

function GroupTab({ groups }: { groups: any[] }) {
  const g = groups[0];
  const glog = useChat((s) => (g ? s.group[g.group_id] ?? [] : []));
  if (!g) return <div style={{ padding: 16, opacity: 0.6 }}>（暂无群）</div>;
  return (
    <>
      <div style={{ padding: "4px 8px", borderBottom: "1px solid #2c3a52" }}><b>{g.name}</b></div>
      <Log lines={glog} />
      <Input placeholder={`在「${g.name}」说…`} onSend={(t) => { net.sendToGroup(g.group_id, t); useChat.getState().pushMine("group", g.group_id, t); }} />
    </>
  );
}

function Profile({ id, names }: { id: number; names: Record<number, string> }) {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    const off = net.onTimeline((aid, d) => { if (aid === id) setData(d); });
    net.fetchTimeline(id);
    return () => { off(); };
  }, [id]);
  return (
    <div style={profileStyle}>
      <div style={{ ...headerStyle }}>
        <b>📖 {names[id] ?? id} 的档案</b>
        <span style={{ cursor: "pointer" }} onClick={() => useUi.getState().closeProfile()}>✕</span>
      </div>
      <div style={{ ...logStyle, height: 360 }}>
        {!data && <div style={{ opacity: 0.5 }}>加载中…</div>}
        {data?.entries?.map((e: any, i: number) => (
          <div key={i} style={{ margin: "3px 0" }}>
            <span style={{ color: "#8af" }}>{e.time}</span> {e.text}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---- styles ----
const panelStyle: React.CSSProperties = {
  position: "absolute", right: 14, top: 14, bottom: 14, width: 340,
  background: "rgba(20,26,38,0.94)", color: "#eee", borderRadius: 12,
  display: "flex", flexDirection: "column", boxShadow: "0 6px 24px rgba(0,0,0,0.4)",
  fontSize: 14, overflow: "hidden",
};
const headerStyle: React.CSSProperties = {
  display: "flex", justifyContent: "space-between", alignItems: "center",
  padding: "10px 12px", borderBottom: "1px solid #2c3a52", fontSize: 15,
};
const tabsStyle: React.CSSProperties = { display: "flex", gap: 4, padding: 8 };
const logStyle: React.CSSProperties = {
  flex: 1, overflowY: "auto", padding: "6px 10px", lineHeight: 1.4,
  background: "rgba(0,0,0,0.2)", margin: "0 8px", borderRadius: 6, minHeight: 120,
};
const inputStyle: React.CSSProperties = {
  flex: 1, padding: "6px 8px", borderRadius: 6, border: "1px solid #3a4a63",
  background: "#11161f", color: "#eee", fontSize: 13, outline: "none",
};
const btnStyle: React.CSSProperties = {
  padding: "6px 12px", borderRadius: 6, border: "none", background: "#4a78c0", color: "#fff", cursor: "pointer",
};
const profileStyle: React.CSSProperties = {
  position: "absolute", left: "50%", top: "50%", transform: "translate(-50%,-50%)",
  width: 420, maxHeight: "80%", background: "rgba(20,26,38,0.97)", color: "#eee",
  borderRadius: 12, display: "flex", flexDirection: "column", boxShadow: "0 6px 30px rgba(0,0,0,0.5)",
};

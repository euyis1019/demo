import { useWorld } from "../store/worldStore";
import { useChat, type Line } from "../store/chatStore";
import {
  dayPhase, NPC_TENDENCY, NPC_COLORS, PLACE_NAMES, affinityLevel,
} from "../config";

// HUD：时辰牌 / 世界事件 / 街坊去向卡 / 连接状态 / 操作提示（React DOM 覆盖 Canvas）。
export default function Hud() {
  const worldTime = useWorld((s) => s.worldTime);
  const worldEvent = useWorld((s) => s.worldEvent);
  const connected = useWorld((s) => s.connected);
  const hello = useWorld((s) => s.hello);
  const agents = useWorld((s) => s.agents);
  const playerId = useWorld((s) => s.playerId);

  const phase = dayPhase(worldTime);
  const npcIds = hello
    ? Object.keys(hello.agents).map(Number).filter((id) => id !== playerId)
    : [];

  // 小镇人情温度 = 三人对玩家好感均值（焐心小镇支柱3 进度轴）
  const affs = npcIds
    .map((id) => agents[String(id)]?.affinity_to_player)
    .filter((v): v is number => typeof v === "number");
  const warmth = affs.length ? Math.round(affs.reduce((a, b) => a + b, 0) / affs.length) : 0;

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", color: "#fff" }}>
      {/* 左上：时辰牌 */}
      <div style={{ position: "absolute", top: 12, left: 14, ...panel, fontSize: 16 }}>
        {phase.icon} {worldTime || "--:--"}{phase.label ? ` · ${phase.label}` : ""}
      </div>
      {worldEvent && (
        <div style={{ position: "absolute", top: 50, left: 14, maxWidth: 280, ...panel, color: "#d9f0c0" }}>
          🍃 {worldEvent}
        </div>
      )}

      {/* 右上：街坊去向卡（含小镇人情温度）*/}
      {npcIds.length > 0 && (
        <div style={{ position: "absolute", top: 12, right: 14, width: 210, ...panel, padding: "8px 12px" }}>
          <WarmthBar warmth={warmth} />
          <div style={{ fontSize: 13, opacity: 0.85, margin: "6px 0 4px" }}>📍 街坊去向</div>
          {npcIds.map((id) => {
            const a = agents[String(id)] || {};
            const name = hello?.agents?.[String(id)] ?? String(id);
            const loc = a.location ? (PLACE_NAMES[a.location] ?? a.location) : "？";
            const aff = a.affinity_to_player;
            return (
              <div key={id} style={{ margin: "5px 0" }}>
                <div style={{ fontSize: 13 }}>
                  <span style={{ color: NPC_COLORS[id] }}>●</span> {name} · {loc}
                  {typeof aff === "number" && (
                    <span style={{ color: "#e88", marginLeft: 6 }}>♥{affinityLevel(aff)}</span>
                  )}
                </div>
                <div style={{ fontSize: 11, opacity: 0.55 }}>{NPC_TENDENCY[id] ?? ""}</div>
              </div>
            );
          })}
        </div>
      )}

      {!connected && (
        <div style={{ position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)", ...panel, color: "#ffb0a8" }}>
          ⚠ 连接中…
        </div>
      )}
      <div style={{ position: "absolute", bottom: 12, left: 14, ...panel, opacity: 0.85 }}>
        WASD/方向键 走动 · 走进区域自动前往 · 走近街坊按 E 私聊 · Tab 打开小镇通
      </div>

      {/* 右下：街坊传闻 feed（口碑流动可见——焐心小镇支柱4）*/}
      <RumorFeed groupId={hello?.groups?.[0]?.group_id} />
    </div>
  );
}

const WARMTH_LABELS: [number, string][] = [
  [80, "亲如一家"], [60, "热乎"], [40, "渐暖"], [20, "渐渐相识"], [0, "还有些客气"],
];
function warmthLabel(w: number): string {
  for (const [th, name] of WARMTH_LABELS) if (w >= th) return name;
  return "还有些客气";
}

function WarmthBar({ warmth }: { warmth: number }) {
  return (
    <div>
      <div style={{ fontSize: 13, opacity: 0.85, display: "flex", justifyContent: "space-between" }}>
        <span>🔥 小镇人情温度</span>
        <span style={{ opacity: 0.8 }}>{warmthLabel(warmth)}</span>
      </div>
      <div style={{ height: 7, borderRadius: 4, background: "rgba(255,255,255,0.15)", marginTop: 3, overflow: "hidden" }}>
        <div style={{
          width: `${warmth}%`, height: "100%",
          background: "linear-gradient(90deg,#e6738c,#e0a23c)", transition: "width .6s",
        }} />
      </div>
    </div>
  );
}

const EMPTY: Line[] = [];
const mentionsPlayer = (s: string) => /农场主|新来|新邻居|新农场/.test(s);

function RumorFeed({ groupId }: { groupId?: number }) {
  const groupMap = useChat((s) => s.group);
  const log = (groupId != null && groupMap[groupId]) || EMPTY;
  const npcLines = log.filter((l) => l.who !== "我").slice(-3);
  if (!npcLines.length) return null;
  return (
    <div style={{ position: "absolute", bottom: 12, right: 14, width: 240, ...panel, padding: "8px 12px" }}>
      <div style={{ fontSize: 13, opacity: 0.85, marginBottom: 3 }}>💬 街坊传闻</div>
      {npcLines.map((l, i) => (
        <div key={i} style={{
          fontSize: 12, margin: "2px 0", lineHeight: 1.35,
          color: mentionsPlayer(l.text) ? "#ffe6b0" : "#cdd6e0",
        }}>
          <span style={{ opacity: 0.8 }}>{l.who}：</span>{l.text}
        </div>
      ))}
    </div>
  );
}

const panel: React.CSSProperties = {
  background: "rgba(0,0,0,0.4)", borderRadius: 8, padding: "3px 10px",
  fontSize: 15, textShadow: "0 1px 2px rgba(0,0,0,0.6)",
};

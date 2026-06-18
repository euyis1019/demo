import { useWorld } from "../store/worldStore";

// 小镇纪事：每跨一个时段弹一页回顾——本时段谁对你升/降温、谁来串过门。
// 焐心小镇支柱5「日子线」：让"小镇日子一天天过"可被看见。可手动关掉。
export default function DigestModal() {
  const digest = useWorld((s) => s.dailyDigest);
  const clear = useWorld((s) => s.clearDigest);
  if (!digest) return null;

  return (
    <div style={backdrop} onClick={clear}>
      <div style={card} onClick={(e) => e.stopPropagation()}>
        <div style={header}>
          <b>📜 小镇纪事 · 第 {digest.day} 天 · {digest.ended_phase}</b>
          <span style={{ cursor: "pointer" }} onClick={clear}>✕</span>
        </div>
        <div style={{ padding: "10px 16px", fontSize: 14, lineHeight: 1.7 }}>
          <div style={{ marginBottom: 8, color: "#ffd9a0" }}>
            🔥 小镇人情温度：{digest.warmth}/100
          </div>
          {digest.changes.length > 0 ? (
            digest.changes.map((c, i) => (
              <div key={i}>
                <span style={{ color: c.delta > 0 ? "#9fe0a0" : "#e89090" }}>
                  {c.delta > 0 ? "▲" : "▼"} {c.name}
                </span>
                {" "}对你的情分{c.delta > 0 ? "升了" : "淡了"}些（现为「{c.level}」）
              </div>
            ))
          ) : (
            <div style={{ opacity: 0.6 }}>这一时段，街坊们对你的看法没什么变化。</div>
          )}
          {digest.visitors.length > 0 && (
            <div style={{ marginTop: 8, color: "#bcd6ff" }}>
              🚶 这段时间来串过门的：{digest.visitors.join("、")}
            </div>
          )}
        </div>
        <div style={{ padding: "0 16px 12px", fontSize: 12, opacity: 0.55 }}>
          （点别处或 ✕ 关闭，接着过日子）
        </div>
      </div>
    </div>
  );
}

const backdrop: React.CSSProperties = {
  position: "absolute", inset: 0, background: "rgba(0,0,0,0.35)",
  display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60,
};
const card: React.CSSProperties = {
  width: 380, background: "rgba(24,30,44,0.97)", color: "#eee", borderRadius: 14,
  boxShadow: "0 8px 32px rgba(0,0,0,0.5)", overflow: "hidden",
};
const header: React.CSSProperties = {
  display: "flex", justifyContent: "space-between", alignItems: "center",
  padding: "12px 16px", borderBottom: "1px solid #2c3a52", fontSize: 15,
  background: "linear-gradient(90deg,#3a2a1a,#2a2438)",
};

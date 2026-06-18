import { useToast } from "./toastStore";

// 屏幕上方居中的 toast 叠层（升温里程碑高亮）。
export default function Toasts() {
  const list = useToast((s) => s.list);
  return (
    <div style={wrap}>
      {list.map((t) => (
        <div key={t.id} style={t.kind === "milestone" ? milestoneStyle : infoStyle}>
          {t.kind === "milestone" ? "💛 " : ""}
          {t.text}
        </div>
      ))}
    </div>
  );
}

const wrap: React.CSSProperties = {
  position: "absolute", top: 70, left: "50%", transform: "translateX(-50%)",
  display: "flex", flexDirection: "column", gap: 8, alignItems: "center",
  pointerEvents: "none", zIndex: 50,
};
const infoStyle: React.CSSProperties = {
  background: "rgba(20,26,38,0.92)", color: "#fff", padding: "7px 16px",
  borderRadius: 10, fontSize: 14, boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
};
const milestoneStyle: React.CSSProperties = {
  ...infoStyle,
  background: "linear-gradient(90deg,#e0a23c,#e6738c)", fontSize: 16, fontWeight: 700,
};

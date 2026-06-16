import { useWorld } from "../store/worldStore";

// HUD：时钟 / 世界事件 / 连接状态 / 操作提示（React DOM 覆盖 Canvas）。
export default function Hud() {
  const worldTime = useWorld((s) => s.worldTime);
  const worldEvent = useWorld((s) => s.worldEvent);
  const connected = useWorld((s) => s.connected);

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", color: "#fff" }}>
      <div style={{ position: "absolute", top: 12, left: 14, ...panel }}>
        🕐 {worldTime || "--:--"}
      </div>
      {worldEvent && (
        <div style={{ position: "absolute", top: 48, left: 14, ...panel, color: "#d9f0c0" }}>
          🍃 {worldEvent}
        </div>
      )}
      {!connected && (
        <div style={{ position: "absolute", top: 12, right: 14, ...panel, color: "#ffb0a8" }}>
          ⚠ 连接中…
        </div>
      )}
      <div style={{ position: "absolute", bottom: 12, left: 14, ...panel, opacity: 0.85 }}>
        WASD/方向键 走动 · 走进区域自动前往 · Tab 打开小镇通
      </div>
    </div>
  );
}

const panel: React.CSSProperties = {
  background: "rgba(0,0,0,0.4)", borderRadius: 8, padding: "3px 10px",
  fontSize: 15, textShadow: "0 1px 2px rgba(0,0,0,0.6)",
};

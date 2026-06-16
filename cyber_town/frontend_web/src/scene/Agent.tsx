import { useEffect, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import { useWorld } from "../store/worldStore";
import { NPC_COLORS, BUBBLE_SECONDS, anchorOf, groundY } from "../config";
import Character, { MODEL, type Anim } from "./Character";

// NPC：KayKit 真模型 + 动画状态机。快照驱动：location→锚点，useFrame lerp 贴地、
// 移动播 walk、说话播 talk、否则 idle；朝移动方向转身。名牌/中文气泡用 <Html>。
export default function Agent({ id }: { id: number }) {
  const group = useRef<THREE.Group>(null);
  const model = useRef<THREE.Group>(null);
  const agent = useWorld((s) => s.agents[String(id)]);
  const color = NPC_COLORS[id] ?? "#cccccc";

  const [bubble, setBubble] = useState("");
  const [anim, setAnim] = useState<Anim>("idle");
  const bubbleUntil = useRef(0);
  const lastBubble = useRef("");
  const target = useRef(new THREE.Vector3(anchorOf("farm", id)[0], 0, anchorOf("farm", id)[1]));
  const placed = useRef(false);
  const faceRef = useRef(0);

  useEffect(() => {
    const loc = agent?.location;
    if (loc) {
      const [ax, az] = anchorOf(loc, id);
      target.current.set(ax, groundY(ax, az), az);
      if (group.current && !placed.current) {
        group.current.position.copy(target.current);
        placed.current = true;
      }
    }
    const b = (agent?.bubble ?? "") as string;
    if (b && b !== lastBubble.current) {
      lastBubble.current = b;
      setBubble(b.length > 36 ? b.slice(0, 36) + "…" : b);
      bubbleUntil.current = performance.now() / 1000 + BUBBLE_SECONDS;
    }
  }, [agent?.location, agent?.bubble, id]);

  useFrame((_, dt) => {
    const g = group.current;
    if (!g) return;
    const t = target.current;
    const before = new THREE.Vector2(g.position.x, g.position.z);
    g.position.x = THREE.MathUtils.damp(g.position.x, t.x, 3.5, dt);
    g.position.z = THREE.MathUtils.damp(g.position.z, t.z, 3.5, dt);
    g.position.y = groundY(g.position.x, g.position.z);
    const dx = g.position.x - before.x, dz = g.position.z - before.y;
    const moving = Math.hypot(dx, dz) > 0.004;

    // 朝向：移动方向
    if (moving && model.current) {
      faceRef.current = Math.atan2(dx, dz);
      model.current.rotation.y = faceRef.current;
    }
    // 气泡到期
    const bubbleOn = bubble && performance.now() / 1000 <= bubbleUntil.current;
    if (bubble && !bubbleOn) setBubble("");
    // 动画状态
    const want: Anim = moving ? "walk" : bubbleOn ? "talk" : "idle";
    if (want !== anim) setAnim(want);
  });

  if (!agent) return null;
  const name = agent.name ?? `村民${id}`;

  return (
    <group ref={group}>
      <group ref={model}>
        <Character url={MODEL[id] ?? MODEL[3]} anim={anim} />
      </group>
      <Html position={[0, 2.1, 0]} center occlude={false} pointerEvents="none">
        <div style={tagStyle(color)}>{name}</div>
      </Html>
      {bubble && (
        <Html position={[0, 2.6, 0]} center occlude={false} pointerEvents="none">
          <div style={bubbleStyle}>{bubble}</div>
        </Html>
      )}
    </group>
  );
}

function tagStyle(color: string): React.CSSProperties {
  return {
    background: "rgba(0,0,0,0.55)", color: "#fff", border: `2px solid ${color}`,
    borderRadius: 8, padding: "1px 8px", fontSize: 13, whiteSpace: "nowrap", fontWeight: 600,
    transform: "translateY(-50%)",
  };
}
const bubbleStyle: React.CSSProperties = {
  background: "rgba(255,253,240,0.96)", color: "#1a1a1a", border: "2px solid #d8b25a",
  borderRadius: 10, padding: "5px 10px", fontSize: 13, width: 168, textAlign: "center",
  whiteSpace: "normal", wordBreak: "break-word", lineHeight: 1.4,
  boxShadow: "0 2px 6px rgba(0,0,0,0.25)",
};

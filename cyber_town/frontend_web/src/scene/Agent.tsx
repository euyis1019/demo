import { useEffect, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import { useWorld } from "../store/worldStore";
import { NPC_COLORS, NPC_SPEED, BUBBLE_SECONDS, anchorOf, groundY } from "../config";

// M-web0/1：NPC 用胶囊占位（M-web3 换 KayKit GLTF）。快照驱动：location→锚点，
// useFrame lerp 贴地移动；bubble 非空→<Html> 头顶中文气泡；名牌常驻。
export default function Agent({ id }: { id: number }) {
  const group = useRef<THREE.Group>(null);
  const agent = useWorld((s) => s.agents[String(id)]);
  const color = NPC_COLORS[id] ?? "#cccccc";

  const [bubble, setBubble] = useState<string>("");
  const bubbleUntil = useRef(0);
  const lastBubble = useRef<string>("");

  // 目标 XZ（按 location 取该 agent 的固定锚点，3 个 NPC 用 id 错开）
  const target = useRef(new THREE.Vector3(anchorOf("farm", id)[0], 0, anchorOf("farm", id)[1]));
  const placed = useRef(false);

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
    const tgt = target.current;
    g.position.x = THREE.MathUtils.damp(g.position.x, tgt.x, 3.5, dt);
    g.position.z = THREE.MathUtils.damp(g.position.z, tgt.z, 3.5, dt);
    g.position.y = groundY(g.position.x, g.position.z);
    if (bubble && performance.now() / 1000 > bubbleUntil.current) setBubble("");
  });

  if (!agent) return null;
  const name = agent.name ?? `村民${id}`;

  return (
    <group ref={group}>
      {/* 占位角色：胶囊身体 + 头 */}
      <mesh position={[0, 0.75, 0]} castShadow>
        <capsuleGeometry args={[0.32, 0.7, 6, 12]} />
        <meshStandardMaterial color={color} roughness={0.8} />
      </mesh>
      <mesh position={[0, 1.45, 0]} castShadow>
        <sphereGeometry args={[0.28, 16, 16]} />
        <meshStandardMaterial color={"#ffe0bd"} roughness={0.7} />
      </mesh>
      {/* 名牌 */}
      <Html position={[0, 2.0, 0]} center occlude={false} pointerEvents="none">
        <div style={tagStyle(color)}>{name}</div>
      </Html>
      {/* 气泡 */}
      {bubble && (
        <Html position={[0, 2.5, 0]} center occlude={false} pointerEvents="none">
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
  borderRadius: 10, padding: "4px 9px", fontSize: 13, maxWidth: 200, textAlign: "center",
  lineHeight: 1.35, boxShadow: "0 2px 6px rgba(0,0,0,0.25)",
};

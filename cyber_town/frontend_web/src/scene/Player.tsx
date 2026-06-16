import { useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import { useWorld } from "../store/worldStore";
import {
  NPC_COLORS, PLAYER_SPAWN, PLAYER_SPEED, WORLD, groundY, placeAt,
} from "../config";
import { net } from "../net/ws";
import { playerRef } from "./playerRef";
import { isUiFocused } from "../ui/uiState";
import Character, { MODEL, type Anim } from "./Character";

const keys: Record<string, boolean> = {};
window.addEventListener("keydown", (e) => (keys[e.code] = true));
window.addEventListener("keyup", (e) => (keys[e.code] = false));

// M-web1：玩家 WASD 在 XZ 走动、贴地；走进地块（内缩矩形滞后）自动发 request_move。
export default function Player() {
  const group = useRef<THREE.Group>(null);
  const model = useRef<THREE.Group>(null);
  const pendingRef = useRef<string>("");
  const pendingSince = useRef(0);
  const [anim, setAnim] = useState<Anim>("idle");

  useFrame((_, dt) => {
    const g = group.current;
    if (!g) return;
    let ix = 0, iz = 0;
    if (!isUiFocused()) {
      if (keys["KeyD"] || keys["ArrowRight"]) ix += 1;
      if (keys["KeyA"] || keys["ArrowLeft"]) ix -= 1;
      if (keys["KeyS"] || keys["ArrowDown"]) iz += 1;
      if (keys["KeyW"] || keys["ArrowUp"]) iz -= 1;
    }
    const moving = !!(ix || iz);
    if (moving) {
      const len = Math.hypot(ix, iz);
      playerRef.x += (ix / len) * PLAYER_SPEED * dt;
      playerRef.z += (iz / len) * PLAYER_SPEED * dt;
      playerRef.x = THREE.MathUtils.clamp(playerRef.x, WORLD.x + 1, WORLD.x + WORLD.w - 1);
      playerRef.z = THREE.MathUtils.clamp(playerRef.z, WORLD.z + 1, WORLD.z + WORLD.d - 1);
      if (model.current) model.current.rotation.y = Math.atan2(ix / len, iz / len);
    }
    if ((moving ? "walk" : "idle") !== anim) setAnim(moving ? "walk" : "idle");
    g.position.set(playerRef.x, groundY(playerRef.x, playerRef.z), playerRef.z);

    // 进区检测 → request_move（内缩矩形滞后；与已确认地点不同才发）
    const now = performance.now() / 1000;
    if (pendingRef.current && now - pendingSince.current > 8) pendingRef.current = "";
    const confirmed = useWorld.getState().agents[String(useWorld.getState().playerId)]?.location ?? "";
    if (pendingRef.current && confirmed === pendingRef.current) pendingRef.current = "";
    const zone = placeAt(playerRef.x, playerRef.z, 2.5);
    if (zone && zone !== confirmed && zone !== pendingRef.current) {
      if (net.requestMove(zone)) {
        pendingRef.current = zone;
        pendingSince.current = now;
      }
    }
  });

  return (
    <group ref={group} position={[PLAYER_SPAWN[0], 0, PLAYER_SPAWN[1]]}>
      <group ref={model}>
        <Character url={MODEL[0]} anim={anim} />
      </group>
      <Html position={[0, 2.1, 0]} center occlude={false} pointerEvents="none">
        <div style={{
          background: "rgba(0,0,0,0.55)", color: "#fff", border: `2px solid ${NPC_COLORS[0]}`,
          borderRadius: 8, padding: "1px 8px", fontSize: 13, whiteSpace: "nowrap", fontWeight: 600,
          transform: "translateY(-50%)",
        }}>我</div>
      </Html>
    </group>
  );
}

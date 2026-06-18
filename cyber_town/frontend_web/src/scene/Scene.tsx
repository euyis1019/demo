import { useWorld } from "../store/worldStore";
import { dayPhase } from "../config";
import Ground from "./Ground";
import Props from "./Props";
import Agent from "./Agent";
import Player from "./Player";
import CameraRig from "./CameraRig";

// 时段光照档（焐心小镇支柱2：作息节律可见——清晨柔黄、晌午明亮、傍晚橙暖、夜里幽蓝）
const LIGHTING: Record<string, {
  sky: string; hemiSky: string; hemi: number; ambient: number; sun: number; sunColor: string;
}> = {
  清晨: { sky: "#bcd9f0", hemiSky: "#dCeBff", hemi: 0.7, ambient: 0.3, sun: 1.15, sunColor: "#ffe6c0" },
  晌午: { sky: "#9ec5e8", hemiSky: "#cfe8ff", hemi: 0.7, ambient: 0.25, sun: 1.5, sunColor: "#fff3d6" },
  傍晚: { sky: "#d8a878", hemiSky: "#f0d0b0", hemi: 0.6, ambient: 0.28, sun: 1.05, sunColor: "#ff9d5c" },
  夜里: { sky: "#1f2a44", hemiSky: "#2a3a5a", hemi: 0.4, ambient: 0.2, sun: 0.45, sunColor: "#8aa0d8" },
};

// 场景根：光照（随时段）+ 地形 + 静态物 + 玩家 + NPC + 相机。
export default function Scene() {
  const hello = useWorld((s) => s.hello);
  const playerId = useWorld((s) => s.playerId);
  const worldTime = useWorld((s) => s.worldTime);
  const npcIds = hello
    ? Object.keys(hello.agents).map(Number).filter((id) => id !== playerId)
    : [];
  const L = LIGHTING[dayPhase(worldTime).label] ?? LIGHTING["晌午"];

  return (
    <>
      <color attach="background" args={[L.sky]} />
      <hemisphereLight args={[L.hemiSky, "#5a6b3a", L.hemi]} />
      <ambientLight intensity={L.ambient} />
      <directionalLight
        position={[18, 30, 12]}
        intensity={L.sun}
        color={L.sunColor}
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-left={-50}
        shadow-camera-right={50}
        shadow-camera-top={50}
        shadow-camera-bottom={-50}
        shadow-camera-near={1}
        shadow-camera-far={120}
        shadow-bias={-0.0004}
      />
      <Ground />
      <Props />
      <Player />
      {npcIds.map((id) => <Agent key={id} id={id} />)}
      <CameraRig />
    </>
  );
}

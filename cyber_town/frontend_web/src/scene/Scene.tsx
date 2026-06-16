import { useWorld } from "../store/worldStore";
import Ground from "./Ground";
import Props from "./Props";
import Agent from "./Agent";
import Player from "./Player";
import CameraRig from "./CameraRig";

// 场景根：光照 + 地形 + 静态物 + 玩家 + NPC + 相机。
export default function Scene() {
  const hello = useWorld((s) => s.hello);
  const playerId = useWorld((s) => s.playerId);
  const npcIds = hello
    ? Object.keys(hello.agents).map(Number).filter((id) => id !== playerId)
    : [];

  return (
    <>
      <hemisphereLight args={["#cfe8ff", "#5a6b3a", 0.7]} />
      <ambientLight intensity={0.25} />
      <directionalLight
        position={[18, 30, 12]}
        intensity={1.4}
        color={"#fff3d6"}
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

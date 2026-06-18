import { useEffect, useMemo, useRef } from "react";
import { useGLTF, useAnimations } from "@react-three/drei";
import { clone as skeletonClone } from "three/examples/jsm/utils/SkeletonUtils.js";
import * as THREE from "three";

// KayKit Adventurers 角色（已绑骨+76 动画）。useGLTF 加载 + SkeletonUtils 克隆（多实例安全）
// + useAnimations 状态机：idle/walk/talk 交叉淡入。
// idle/walk/talk + 活动动画（B1：让 NPC 不说话也看着在过日子）
export type Anim = "idle" | "walk" | "talk" | "work" | "sit" | "lie" | "cheer";
const CLIP: Record<Anim, string> = {
  idle: "Idle", walk: "Walking_A", talk: "Interact",
  work: "Use_Item", sit: "Sit_Floor_Idle", lie: "Lie_Idle", cheer: "Cheer",
};

// agent_id → KayKit 模型（0 玩家=骑士 / 1 老钱=法师 / 2 阿香=盗贼 / 3 大山=蛮族）
export const MODEL: Record<number, string> = {
  0: "models/Knight.glb",
  1: "models/Mage.glb",
  2: "models/Rogue.glb",
  3: "models/Barbarian.glb",
};
Object.values(MODEL).forEach((u) => useGLTF.preload(u));

export default function Character({
  url, anim, faceAngle = 0, scale = 1.1,
}: { url: string; anim: Anim; faceAngle?: number; scale?: number }) {
  const { scene, animations } = useGLTF(url);
  const cloned = useMemo(() => {
    const c = skeletonClone(scene);
    c.traverse((o) => {
      if ((o as THREE.Mesh).isMesh) {
        o.castShadow = true;
        o.receiveShadow = true;
      }
    });
    return c;
  }, [scene]);
  const ref = useRef<THREE.Group>(null);
  const { actions } = useAnimations(animations, ref);

  useEffect(() => {
    const act = actions[CLIP[anim]] ?? actions["Idle"];
    if (!act) return;
    act.reset().fadeIn(0.2).play();
    return () => { act.fadeOut(0.2); };
  }, [anim, actions]);

  return (
    <group ref={ref} rotation-y={faceAngle} scale={scale}>
      <primitive object={cloned} />
    </group>
  );
}

import { useMemo } from "react";
import { useGLTF } from "@react-three/drei";
import { clone as skeletonClone } from "three/examples/jsm/utils/SkeletonUtils.js";
import * as THREE from "three";
import { groundY } from "../config";

// 通用静态 GLB 模型：useGLTF 加载 + clone（同模型可多处摆放）+ 开投影 + 自动贴地。
export default function Model({
  url, pos, rot = 0, scale = 1, yOffset = 0,
}: { url: string; pos: [number, number]; rot?: number; scale?: number; yOffset?: number }) {
  const { scene } = useGLTF(url);
  const obj = useMemo(() => {
    const c = skeletonClone(scene);
    c.traverse((o) => {
      if ((o as THREE.Mesh).isMesh) { o.castShadow = true; o.receiveShadow = true; }
    });
    return c;
  }, [scene]);
  return (
    <primitive
      object={obj}
      position={[pos[0], groundY(pos[0], pos[1]) + yOffset, pos[1]]}
      rotation-y={rot}
      scale={scale}
    />
  );
}

export const env = (name: string) => `models/env/${name}.glb`;

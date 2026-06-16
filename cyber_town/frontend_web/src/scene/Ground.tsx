import { useMemo } from "react";
import * as THREE from "three";
import { PLACE_CENTER, PLACE_RECTS, WORLD, groundY } from "../config";

// M-web0：灰盒地形——整块草地 + 三地点不同色地块。M-web3 换真 3D 地形/铺装。
function GroundPlane({
  cx, cz, w, d, color, y = 0.02,
}: { cx: number; cz: number; w: number; d: number; color: string; y?: number }) {
  return (
    <mesh rotation-x={-Math.PI / 2} position={[cx, y, cz]} receiveShadow>
      <planeGeometry args={[w, d]} />
      <meshStandardMaterial color={color} roughness={1} />
    </mesh>
  );
}

export default function Ground() {
  // 起伏大地面（细分网格 + 顶点高度），meshStandardMaterial 受光产生明暗
  const geo = useMemo(() => {
    const g = new THREE.PlaneGeometry(WORLD.w, WORLD.d, 64, 28);
    g.rotateX(-Math.PI / 2);
    const pos = g.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const z = pos.getZ(i);
      pos.setY(i, groundY(x, z));
    }
    g.computeVertexNormals();
    return g;
  }, []);

  return (
    <group>
      <mesh geometry={geo} position={[WORLD.x + WORLD.w / 2, 0, WORLD.z + WORLD.d / 2]} receiveShadow>
        <meshStandardMaterial color="#6cae54" roughness={1} />
      </mesh>
      {/* 三地点地块（略抬，区分材质）*/}
      {Object.entries(PLACE_RECTS).map(([pid, r]) => {
        const [cx, cz] = PLACE_CENTER[pid];
        const color = pid === "square" ? "#caa46a" : pid === "saloon" ? "#b98b5e" : "#7ab85f";
        return <GroundPlane key={pid} cx={cx} cz={cz} w={r.w * 0.7} d={r.d * 0.7} color={color} y={0.04} />;
      })}
    </group>
  );
}

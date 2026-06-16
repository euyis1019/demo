import { PLACE_CENTER, groundY } from "../config";

// M-web0 占位静态物：房子(box) + 树(锥+柱)。M-web3 换 KayKit/Kenney GLTF。
function Tree({ x, z }: { x: number; z: number }) {
  const y = groundY(x, z);
  return (
    <group position={[x, y, z]}>
      <mesh position={[0, 0.5, 0]} castShadow>
        <cylinderGeometry args={[0.12, 0.16, 1, 6]} />
        <meshStandardMaterial color="#7a5230" roughness={1} />
      </mesh>
      <mesh position={[0, 1.5, 0]} castShadow>
        <coneGeometry args={[0.9, 1.8, 8]} />
        <meshStandardMaterial color="#3f8f43" roughness={1} />
      </mesh>
    </group>
  );
}

function House({ x, z, color }: { x: number; z: number; color: string }) {
  const y = groundY(x, z);
  return (
    <group position={[x, y, z]}>
      <mesh position={[0, 1.1, 0]} castShadow receiveShadow>
        <boxGeometry args={[4, 2.2, 3.4]} />
        <meshStandardMaterial color={color} roughness={0.9} />
      </mesh>
      <mesh position={[0, 2.6, 0]} castShadow rotation-y={Math.PI / 4}>
        <coneGeometry args={[3.2, 1.4, 4]} />
        <meshStandardMaterial color="#9c4a2f" roughness={1} />
      </mesh>
    </group>
  );
}

export default function Props() {
  const trees: [number, number][] = [
    [-40, -13], [-38, 13], [40, -12], [38, 14], [-20, -14], [20, 14],
    [0, -15], [12, 15], [-12, 14], [-34, 4], [34, -4],
  ];
  return (
    <group>
      <House x={PLACE_CENTER.farm[0] - 2} z={-11} color="#caa06a" />
      <House x={PLACE_CENTER.saloon[0] + 2} z={10} color="#b06a52" />
      <House x={6} z={-10} color="#b5a07a" />
      {trees.map(([x, z], i) => <Tree key={i} x={x} z={z} />)}
    </group>
  );
}

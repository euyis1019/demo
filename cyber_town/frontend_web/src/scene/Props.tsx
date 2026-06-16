import { useGLTF } from "@react-three/drei";
import Model, { env } from "./Model";

// 全 3D 环境：Quaternius 中世纪村庄 + 自然 + 作物（CC0 GLB）。三地点各自建筑 + 道具，
// 林缘散布树/石/灌木，农场菜畦铺作物，草地点缀花草。

// 预加载用到的环境模型
const USED = [
  "House_1", "House_2", "Inn", "Stable", "Mill", "Well", "MarketStand_1", "MarketStand_2",
  "Cart", "Barrel", "Hay", "Fence", "Bench_1", "Gazebo", "Bonfire_Lit",
  "CommonTree_1", "CommonTree_3", "CommonTree_5", "PineTree_2", "PineTree_4",
  "Bush_1", "Bush_2", "Rock_1", "Rock_3", "Rock_5", "TreeStump",
  "Corn_2", "Wheat_2", "Carrot_2", "Pumpkin_2", "Tomato_2",
  "Flower_1", "Flower_2", "Flower_3", "Flower_4", "Grass_1", "Grass_2",
];
USED.forEach((n) => useGLTF.preload(env(n)));

// mulberry32 确定性随机（散点稳定可截图回归）
function rng(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const TREES = ["CommonTree_1", "CommonTree_3", "CommonTree_5", "PineTree_2", "PineTree_4"];
const ROCKS = ["Rock_1", "Rock_3", "Rock_5"];
const FLOWERS = ["Flower_1", "Flower_2", "Flower_3", "Flower_4"];
const CROPS = ["Corn_2", "Wheat_2", "Carrot_2", "Pumpkin_2", "Tomato_2"];

export default function Props() {
  const r = rng(20260616);

  // —— 三地点建筑 + 道具 ——
  const buildings: [string, [number, number], number, number][] = [
    // 农场：农舍 + 牲口棚 + 风车 + 货车 + 干草（建筑靠地块后侧，不挡玩家）
    ["House_1", [-34, -11], 0.5, 1.6],
    ["Stable", [-24, -12], 0, 1.5],
    ["Mill", [-40, 9], 0.4, 1.7],
    ["Cart", [-18, 8], 1.2, 1.3],
    ["Hay", [-16, 10], 0, 1.2], ["Hay", [-20, 11], 0.5, 1.1],
    // 广场：水井(中心) + 两个集市摊 + 凉亭 + 长椅 + 篝火
    ["Well", [0, 4], 0, 1.4],
    ["MarketStand_1", [-6, -5], 0.4, 1.4], ["MarketStand_2", [6, -5], -0.4, 1.4],
    ["Gazebo", [6, 7], 0, 1.6], ["Bench_1", [-6, 6], 0, 1.3],
    ["Bonfire_Lit", [0, -7], 0, 1.2],
    // 酒馆：客栈(后侧) + 酒桶 + 长椅
    ["Inn", [34, 12], Math.PI, 1.7],
    ["Barrel", [22, -2], 0, 1.3], ["Barrel", [23.2, -2.6], 0.7, 1.3],
    ["Bench_1", [20, 3], Math.PI / 2, 1.3],
  ];

  // —— 农场菜畦作物（3 排 × n 列）——
  const beds: [string, [number, number], number, number][] = [];
  for (let row = 0; row < 3; row++) {
    const z = -7 + row * 5;
    const crop = CROPS[row % CROPS.length];
    for (let i = 0; i < 6; i++) {
      const x = -35 + i * 2;
      beds.push([crop, [x, z], 0, 1.0]);
    }
  }

  // —— 林缘散树/石/灌木（避开三地块中心带）——
  const nature: [string, [number, number], number, number][] = [];
  const edges: [number, number][] = [];
  for (let i = 0; i < 26; i++) {
    const x = -43 + r() * 86;
    const onEdge = Math.abs(Math.abs(((x + 9) % 28) - 14)) > 9 || r() < 0.4;
    const z = (r() < 0.5 ? -1 : 1) * (11 + r() * 5);  // 上下边缘带
    edges.push([x, z]);
  }
  edges.forEach(([x, z], i) => {
    const pick = r();
    const name = pick < 0.6 ? TREES[i % TREES.length] : pick < 0.8 ? ROCKS[i % ROCKS.length] : (r() < 0.5 ? "Bush_1" : "Bush_2");
    const s = name.includes("Tree") ? 1.0 + r() * 0.4 : name.includes("Rock") ? 0.9 + r() * 0.8 : 1.1;
    nature.push([name, [x, z], r() * Math.PI * 2, s]);
  });
  // 几棵点睛树在地块之间
  nature.push(["CommonTree_1", [-11, -8], 0.3, 1.3], ["PineTree_4", [11, 7], 1.0, 1.3],
    ["CommonTree_5", [-12, 9], 2.0, 1.2], ["TreeStump", [-9, 3], 0, 1.1]);

  // —— 草地点缀花草 ——
  const flora: [string, [number, number], number, number][] = [];
  for (let i = 0; i < 46; i++) {
    const x = -42 + r() * 84;
    const z = -15 + r() * 30;
    // 跳过广场中心与路带
    if (Math.hypot(x, z) < 8) continue;
    if (Math.abs(z) < 2.2) continue;
    const name = r() < 0.6 ? FLOWERS[i % FLOWERS.length] : (r() < 0.5 ? "Grass_1" : "Grass_2");
    flora.push([name, [x, z], r() * Math.PI * 2, 0.8 + r() * 0.5]);
  }

  const all = [...buildings, ...beds, ...nature, ...flora];
  return (
    <group>
      {all.map(([name, pos, rot, scale], i) => (
        <Model key={i} url={env(name)} pos={pos} rot={rot} scale={scale} />
      ))}
    </group>
  );
}

import { Suspense, useEffect } from "react";
import { Canvas } from "@react-three/fiber";
import { Loader } from "@react-three/drei";
import { CAM_SIZE } from "./config";
import Scene from "./scene/Scene";
import Hud from "./ui/Hud";
import PhoneMenu from "./ui/PhoneMenu";
import { net } from "./net/ws";
import { useWorld } from "./store/worldStore";

// 调试：暴露 store/net（截图核验用，生产无害）
(window as any).__world = useWorld;
(window as any).__net = net;

export default function App() {
  useEffect(() => {
    net.start();
  }, []);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Canvas
        shadows
        orthographic
        camera={{ position: [-28, 16, 21], zoom: 1, near: -100, far: 200 }}
        gl={{ antialias: true }}
        style={{ background: "#9ec5e8" }}
      >
        <Suspense fallback={null}>
          <Scene />
        </Suspense>
      </Canvas>
      <Hud />
      <PhoneMenu />
      <Loader />
    </div>
  );
}

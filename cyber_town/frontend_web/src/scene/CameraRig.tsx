import { useThree, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { useEffect } from "react";
import { CAM_SIZE, groundY } from "../config";
import { playerRef } from "./playerRef";

// 正交相机斜俯视（复刻星露谷视角），平滑跟随玩家。
export default function CameraRig() {
  const { camera, size } = useThree();

  useEffect(() => {
    const cam = camera as THREE.OrthographicCamera;
    const aspect = size.width / size.height;
    cam.left = (-CAM_SIZE * aspect) / 2;
    cam.right = (CAM_SIZE * aspect) / 2;
    cam.top = CAM_SIZE / 2;
    cam.bottom = -CAM_SIZE / 2;
    cam.near = -100;
    cam.far = 200;
    cam.updateProjectionMatrix();
  }, [camera, size]);

  useFrame((_, dt) => {
    const px = playerRef.x, pz = playerRef.z;
    const py = groundY(px, pz);
    // 偏移更斜（俯角 ~38°，没那么垂直）、更远（看得更广）
    const desired = new THREE.Vector3(px + 0, py + 15, pz + 19);
    camera.position.x = THREE.MathUtils.damp(camera.position.x, desired.x, 6, dt);
    camera.position.y = THREE.MathUtils.damp(camera.position.y, desired.y, 6, dt);
    camera.position.z = THREE.MathUtils.damp(camera.position.z, desired.z, 6, dt);
    camera.lookAt(px, py + 0.8, pz);
  });
  return null;
}

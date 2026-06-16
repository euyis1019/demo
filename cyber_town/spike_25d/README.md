# 2.5D 伪 3D Spike（独立验证工程）

> 目的：验证「**正交 3D 相机俯视 + 纹理 3D 地面 + 真实光影 + 现有像素角色做
> billboard 立绘**」这条伪 3D 路线的观感与 Web 可行性（见 [docs/3D可行性调研.md](../../docs/3D可行性调研.md) 推荐方案 B1）。
> **独立工程，不依赖后端、不影响 `cyber_town/frontend` 的 2D 正式版。**

## 怎么跑

```bash
# 桌面直接跑
godot --path cyber_town/spike_25d

# 导出 Web 后浏览器跑（Compatibility/WebGL2）
godot --headless --path cyber_town/spike_25d \
  --export-release "Web" cyber_town/spike_25d/dist/index.html
cd cyber_town/spike_25d/dist && python3 -m http.server 8077
# 浏览器开 http://127.0.0.1:8077/index.html
```

操作：`WASD`/方向键走动（玩家是中间那个，坐标 `Vector3`，对应后端 `Vector2 → (x,0,y)`）。

## 实现要点（`scripts/world3d.gd`，全代码生成，对齐正式版风格）

- **相机**：`Camera3D` 正交（`PROJECTION_ORTHOGONAL`）+ `look_at` 玩家斜上方 ≈ 51° 俯角，跟随玩家。
- **地面**：`PlaneMesh` + 平铺纹理（草地 + 夯土广场，复用现有像素 tile），`TEXTURE_FILTER_NEAREST` 保像素感。
- **光照**：`DirectionalLight3D`(shadow_enabled) + `WorldEnvironment`(ProceduralSky + 天光环境光)。
- **3D 几何**：房子用 `BoxMesh`，投**真实方向光阴影**（证明真 3D 几何可用）。
- **角色**：`AnimatedSprite3D`，`billboard = FIXED_Y`（始终竖直朝相机）、`alpha_cut = DISCARD`、
  `NEAREST`，`SpriteFrames` 由现有 Ninja Adventure 角色帧 4 向构建（复用 2D 美术，无骨骼动画）。
- **树/植被**：`Sprite3D` billboard（Don't Starve 式 2D 立绘进 3D）。
- **接地阴影**：精灵自身关闭投影（扁平 billboard 投影很难看），改用程序化柔和
  `blob.png` 圆形阴影平铺地面——观感更稳。

## 验证结论

- ✅ **Web 能跑**：Compatibility/WebGL2 下 3D 场景正常渲染（截图见提交说明）。
- ✅ **真实光影**：方向光对 3D 盒子产生真阴影；天光环境光自然。
- ✅ **2D 立绘融入 3D**：像素角色/植被作 billboard 站在 3D 地面上、深度遮挡正确、有接地影。
- 📦 **体积**：dist ≈ 36MB，其中 `index.wasm` 37.7MB 是 **Godot 引擎二进制本身**
  （与 2D 版同款），`index.pck`（场景+资产）仅 41KB → **转 3D 几乎不增包体**；
  真正要压的是引擎 wasm（VRAM 压缩 / Basis Universal，见调研文档）。
- ⚠️ **代价**：这是从零搭的最小场景；正式转 3D 需把 `frontend` 的 ~1400 行 2D 表现层
  改写为 3D（坐标 `Vector2→Vector3`、节点 2D→3D、shader 重写），**但后端/WS 协议零改动**。

## 资产
`assets/` 下 `grass/dirt/tree` 由现有 `tileset.png` 裁切、`blob.png` 程序生成、
`char_*.png` 复用正式版角色图（CC0 Ninja Adventure）。

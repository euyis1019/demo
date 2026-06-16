# 2.5D 伪 3D Spike（独立验证工程）

> 目的：验证「**正交 3D 相机俯视 + 纹理 3D 地面 + 真实光影 + 现有像素角色做
> billboard 立绘**」这条伪 3D 路线的观感与 Web 可行性（见 [docs/3D可行性调研.md](../../docs/3D可行性调研.md) 推荐方案 B1）。
> **独立工程，不依赖后端、不影响 `cyber_town/frontend` 的 2D 正式版。**

> **W12 升级：静态场景已全面 3D 化**——地形（起伏网格 + 顶点色 splat 草/泥过渡）、
> 草、花、石头、栅栏、菜畦全部立体构建（程序化网格 / MultiMesh 合批 / 交叉双 quad +
> alpha scissor + 风 shader），角色仍为 billboard 立绘。即「基本全 3D 构建的场景」。
> 实现依据：`docs` 的全 3D 调研方案；落地见 `scripts/world3d.gd`。

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

- **单一真相高度 `height(x,z)`**：地面网格顶点 + 一切贴地物（草/花/石/栅/树/角色/blob 影）
  的 y 全喂它 → 杜绝浮空/陷地。FastNoiseLite ±0.6 缓坡。
- **地形**：`SurfaceTool` 生成起伏 `ArrayMesh`（80×80 格）+ **顶点色 splat `ShaderMaterial`**
  混草/泥纹理（草地↔夯土广场↔菜畦平滑过渡，单 draw call，消灭叠面 z-fighting）。
- **草（海量）**：**交叉双 quad**（两片 90° 相交，斜视有体积、不跟相机转）源 mesh，
  按 10×10m **分块 `MultiMeshInstance3D`**（块级视锥剔除）合批；材质用
  `ALPHA_SCISSOR`(discard，绝不 blend) + `CULL_DISABLED` + `NEAREST` + **风 spatial shader**
  （顶点位移 = 世界相位 + TIME + UV.y mask，草根钉住草尖摆）；关投影。
- **花**：交叉双 quad MultiMesh + `ALPHA_SCISSOR` 静态材质（4 色，程序生成像素花）。
- **石头**：低面 `SphereMesh` MultiMesh，**投真实阴影**。
- **栅栏**：程序化「柱+横档」段 `ArrayMesh` MultiMesh，沿 farm 边界，投阴影。
- **菜畦**：矮 `BoxMesh` 阵列（dirt 纹理），投阴影。
- **房子**：`BoxMesh`，投真实方向光阴影。
- **角色**：`AnimatedSprite3D`（`billboard=FIXED_Y` / `alpha_cut=DISCARD` / `NEAREST`），
  `SpriteFrames` 由现有 Ninja Adventure 角色帧 4 向构建（复用 2D 美术、无骨骼动画）。
- **树**：`Sprite3D` billboard（Don't Starve 式）。
- **阴影策略**：只「房子/石头/栅栏/菜畦」等实心几何投真实阴影；草/花/角色/树一律
  关投影 + 程序化柔和 `blob` 接地影（草不需要 blob）。
- **性能 HUD**：左上实时显示 FPS / draw_calls / tris（先有标尺再加量）。

## 验证结论（Chrome headless WebGL2）

- ✅ **全 3D 静态场景成立**：起伏地形 + splat 草泥过渡 + 海量立体草丛 + 花 + 石 + 栅栏 +
  菜畦 + 房子全部 3D 构建；角色 billboard 融入，深度/遮挡/接地正确。
- ✅ **真实光影**：硬几何投方向光阴影；天光环境光自然。
- 📊 **性能健康**：draw_calls ≈ **48**、tris ≈ **2.3 万**（约 5000 株草 + 360 朵花 + 石/栅/菜畦）。
  ⚠️ headless 的 FPS 低是 **SwiftShader 软件渲染（无 GPU）**所致，**不代表真机**；
  draw call / 三角形数才是真实指标，均在 web 安全区间，真显卡轻松 60fps。
- 📦 **体积**：dist ≈ 36MB，几乎全是 `index.wasm`（引擎本身，与 2D 同款）；
  场景+资产 pck 仅几十 KB → 全 3D 化几乎不增包体。
- ⚠️ **正式落地代价**：本工程是独立验证；接回正式版需把 `frontend` 表现层改写为 3D
  并接 WebSocket 快照（坐标 `Vector2→Vector3(x,0,y)`），**后端/协议零改动**。

## 必守坑（来自调研，已在代码遵守）
草用 alpha **scissor 不用 blend**；**分块** MultiMesh（非巨型，才有视锥剔除）；
草/billboard **不投阴影**；mesh 只在 `_ready` 建一次（`_process` 不重建）；
风 shader **不用 `depth_prepass_alpha`**（web 不支持）；像素图 **不开 mipmap**、
平铺用**独立 PNG**（非 AtlasTexture 子区）；地形高度走 **CPU `height()` 不走 shader 位移**。

## 资产
`assets/` 下 `grass/dirt/path/tree/grasstuft*` 由现有 `tileset.png` 裁切；
`blade/flower_*`（草叶/4 色花）与 `blob`（接地影）程序生成；
`char_*.png` 复用正式版角色图（CC0 Ninja Adventure）。

# frontend3d —— 赛博小镇 3D 版前端（完整可玩）

> 伪 3D（2.5D）正式前端：**全 3D 静态场景**（起伏地形 / 草 / 花 / 石 / 栅栏 / 菜畦 /
> 房子全部立体构建）+ **billboard 像素角色立绘**，**快照驱动**接后端，与 2D 版同一套
> WebSocket 协议、**后端零改动**。逻辑坐标映射：后端 `Vector2` → 3D `Vector3(x, ground_y, z)`。

## 运行（后端默认就托管 3D 版）

```bash
cd /Users/dawson/Documents/GitHub/demo-cyber-town
uvicorn cyber_town.backend.main:app --port 8000
# 浏览器开 http://127.0.0.1:8000/game/
```

- 后端 `/game` **默认托管 frontend3d/dist**；`CYBER_TOWN_FRONTEND=2d` 可切回 2D 版。
- 改了前端脚本后需重新导出：
  ```bash
  godot --headless --path cyber_town/frontend3d \
    --export-release "Web" cyber_town/frontend3d/dist/index.html
  ```

操作：`WASD`/方向键走动 · 走进区域自动跨地点 · 走近 NPC 按 `E` 私聊 · `Tab` 开「小镇通」· 点 NPC 看档案。

## 架构（复用 2D 的非视觉层，重写表现层为 3D）

| 复用（与 2D 同款） | 3D 新写 |
|---|---|
| `scripts/world_net.gd`（WS 客户端，autoload）| `scripts/main.gd`：全 3D 世界生成 + 快照分发 + zone→request_move + 正交相机 + 昼夜光 + HUD |
| `scripts/phone_menu.gd`（小镇通 UI，CanvasLayer）| `scripts/player.gd`：3D 键盘走动 + 贴地 + billboard |
| 角色/字体/音频资产 | `scripts/npc.gd`：快照驱动位置/动画 + 名牌/气泡/状态徽章/思考（Label3D billboard）|
| | `scripts/config.gd`：3D 地点布局（XZ）+ `ground_y` 高度单一真相 |
| | `scripts/sprite_lib.gd`：SpriteFrames / 交叉 quad / 草风·splat·scissor 材质 / Label3D 工厂 |

渲染：**Compatibility(WebGL2)**（web 唯一可用），`thread_support=false`。
3D 技法与性能红线见 `../spike_25d/README.md` 与 `docs/3D可行性调研.md`。

## 验证（真实后端 + Chrome WebGL2）

- ✅ 3D 世界渲染、起伏地形 + 草泥过渡 + 海量立体草丛 + 花/石/栅/菜畦/房子
- ✅ 玩家 3D 走动、相机跟随；**走进区域 → 前端发 `request_move`**（后端日志确认 farm/square 切换）
- ✅ NPC 快照驱动：走向地点锚点、四向动画、**中文对话气泡 + 名牌 + 状态徽章 + 思考指示**
- ✅ 小镇通（Tab）聊天 UI 在 3D 场景中正常（F2F/私聊/群聊/档案）
- ✅ 昼夜光（方向光按 world_time 变化）、世界事件 HUD、BGM

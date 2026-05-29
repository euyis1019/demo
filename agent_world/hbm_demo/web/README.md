# F09 / L3 — 前端 (`web/`)

React + Vite + TypeScript 双栏世界舞台 + 可选沉浸式剧情模式。总览/架构见
**[`../README.md`](../README.md)** 与 **[`../ARCHITECTURE.md`](../ARCHITECTURE.md)**。

## 开发

```bash
cd agent_world/hbm_demo/web
npm install
npm run dev        # http://localhost:5173
```

推荐在仓库根目录用 `./agent_world/hbm_demo/scripts/ops/start_demo.sh` 一并启动
Runner + Flask + Vite。API 走 Vite 代理：`/api` → `http://127.0.0.1:5050`
（可用 `VITE_API_PROXY_TARGET` 覆盖）。

## 目录结构

```text
src/
├── App.tsx                  # 根组件：编排各 view（boot/playing/game_over/ending）+ 双栏/剧情切换
├── main.tsx                 # 挂载入口
├── api/                     # HTTP 客户端与类型
│   ├── client.ts            #   apiGet/apiPost 封装
│   ├── hbm.ts               #   各端点调用（player-turn/world-delta/...）
│   ├── types.ts             #   API 请求/响应类型
│   ├── config.ts / errors.ts
├── store/                   # 全局状态
│   ├── gameStore.ts         #   GameState + gameReducer
│   ├── gameStoreContext.ts  #   Context + useGameStoreContext（与 Provider 解耦）
│   ├── GameStoreProvider.tsx#   Provider 组件
│   ├── worldSync.ts         #   世界状态合并（applyWorldDelta/Snapshot、房间 F2F、世界事件）
│   ├── agentInbox.ts        #   「Agent 手机/消息」域（RDC/GRP 线程、RdcLink、社交事件）
│   └── index.ts             #   store 公共出口
├── features/                # 按屏/域拆分（app → features → shared/api/store）
│   ├── boot/                #   启动屏、健康检查、Runner 503 Modal
│   ├── game-loop/           #   回合循环：发回合、world-delta 轮询(F14)、WS(F16)、loop 控制(F13)
│   ├── layout/              #   双栏布局、StatusPanel
│   ├── player-input/        #   玩家输入框
│   ├── world-stage/         #   F12 四房间世界视图（components/ hooks/ lib/）
│   ├── story-mode/          #   沉浸式剧情模式（舞台、对话历史、字幕、绿幕头像）
│   ├── prompt-trace/        #   F15 Prompt Inspector 弹窗
│   ├── endings/             #   结局屏 / Bad End 屏 / Phase Toast
│   ├── shared/              #   跨 feature 共享 UI（MessageBubble）
│   └── index.ts             #   features 公共出口
├── constants/               # 轮询间隔、Phase 过渡、Agent/群组常量、端口
├── utils/                   # 消息 merge/排序、place 映射、聊天布局、apiError
├── lib/                     # 通用纯函数
└── styles/                  # CSS（@import 桶）
    ├── global.css           #   桶：按序 @import 下列三件
    ├── base.css             #   :root/reset/面板/按钮/气泡/toast/loading/503
    ├── world-stage.css      #   世界舞台/agent-phone/prompt-trace
    └── story-mode.css       #   剧情模式/对话历史/字幕/工具栏
```

## 模块边界

- 依赖方向：`app → features → shared(api/store/utils)`；`store` 不依赖 `features`。
- 跨 feature 只能从对方 `index.ts` 公共出口导入，**禁止深引** `*/components|hooks|lib`
  内部文件（eslint `no-restricted-imports` 强制，见 `eslint.config.js`）。
- `store/` 顶层全局；与组件紧耦合的 hook/lib 放在各 feature 内部。

## 同步机制

- **F14**：`game-loop/useWorldDeltaPoll` 轮询 `/world-delta?since_tick=`，
  `worldDeltaApply` 合并增量、回放气泡/移动/世界事件；`game_over.status` 路由到
  EndingScreen(`completed`) 或 GameOverScreen(`game_over`)。
- **F16**：`useWorldDeltaStream` 经 WebSocket 推送（可选）。
- **F12**：`hydrateWorldSnapshot` 初次全量校准。

## 脚本

| 命令 | 说明 |
|------|------|
| `npm run dev` | 开发服务器（:5173） |
| `npm run build` | 生产构建（`tsc -b && vite build`，输出 `dist/`，已 gitignore） |
| `npm run lint` | ESLint（含 feature import 边界规则） |
| `npm run preview` | 预览构建产物 |

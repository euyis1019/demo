# HBM Demo 前端（`web/`）

《HBM 显存价格保卫战》React + Vite 前端。开发规划见 [`dev_logs/21_HBM_Demo后续开发规划_PLAN2.md`](../../../dev_logs/21_HBM_Demo后续开发规划_PLAN2.md)。

## 环境

- Node.js 18+
- 推荐在**仓库根目录**一键启动：`./agent_world/hbm_demo/scripts/start_demo.sh`（见 [`../README.md`](../README.md)）
- 或手动先启动 Runner + Flask，再在本目录 `npm run dev`

## 安装与开发

```bash
cd agent_world/hbm_demo/web
npm install
npm run dev
```

浏览器打开 http://localhost:5173

**25 轮完整试玩**：见 [`dev_logs/19_HBM_Demo_25轮参考台词.md`](../../../dev_logs/19_HBM_Demo_25轮参考台词.md)

API 请求走 Vite 代理：`/api` → `http://127.0.0.1:5050`（HBM Demo 专用端口；`VITE_API_PROXY_TARGET` 可覆盖）。

## 脚本

| 命令 | 说明 |
|------|------|
| `npm run dev` | 开发服务器（端口 5173） |
| `npm run build` | 生产构建 |
| `npm run preview` | 预览构建产物 |

## 目录（规划）

```text
src/
  api/           # F1 — HTTP client（types / client / hbm / errors）
  components/    # F2 — 三屏 UI 壳（layout / panels / overlays）
  mock/          # F2 — 静态 Mock 数据（F3 起由 store 替换）
  utils/         # 消息 merge/sort、place 映射
  constants/     # F3/F4 — 轮询、Phase 过渡、GRP 标签
  store/         # F3 — game state（reducer + provider）
  hooks/         # F3–F5 — game loop / auto-scroll / loading / env-status
  styles/        # global.css
```

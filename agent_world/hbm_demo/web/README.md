# HBM Demo 前端（`web/`）

《HBM 显存价格保卫战》React + Vite 前端。开发规划见上级目录 [`PLAN2.md`](../PLAN2.md)。

## 环境

- Node.js 18+
- 后端：须先启动 Runner + Flask（见 [`../README.md`](../README.md)）

## 安装与开发

```bash
cd agent_world/hbm_demo/web
npm install
npm run dev
```

浏览器打开 http://localhost:5173

API 请求走 Vite 代理：`/api` → `http://127.0.0.1:5000`（无需 CORS）。

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
  store/         # F2+ — game state
  components/    # F2+ — UI
  hooks/         # F3+ — game loop
  styles/        # global.css
```

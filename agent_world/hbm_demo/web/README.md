# HBM Demo 前端（`web/`）

React + Vite + TypeScript。架构与 Feature 说明见 **[`../README.md`](../README.md)**。

## 开发

```bash
cd agent_world/hbm_demo/web
npm install
npm run dev    # http://localhost:5173
```

推荐在仓库根目录使用 `./agent_world/hbm_demo/scripts/start_demo.sh` 同时启动 Runner、Flask 与本 dev server。

API 走 Vite 代理：`/api` → `http://127.0.0.1:5050`（可用 `VITE_API_PROXY_TARGET` 覆盖）。

## 目录

```text
src/
  features/     # F09a–f：boot、game-loop、layout、main-chat、observer、endings、shared
  api/          # HTTP client 与类型
  store/        # gameStore reducer
  constants/    # 轮询、Phase 过渡、GRP 标签
  utils/        # 消息 merge、place 映射
  styles/       # global.css
  App.tsx       # 从 ./features 聚合导入
```

## 脚本

| 命令 | 说明 |
|------|------|
| `npm run dev` | 开发服务器 |
| `npm run build` | 生产构建（输出 `dist/`，已 gitignore） |
| `npm run preview` | 预览构建产物 |

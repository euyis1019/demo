import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

// 产物挂在后端 /game/ 子路径下，base 必须为 /game/（否则 /assets/* 404）。
// 开发态把 /ws、/healthz、/agents 代理到 FastAPI 后端（ws:true 才能升级 WebSocket）。
export default defineConfig({
  base: "/game/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/ws": { target: "ws://localhost:8000", ws: true, changeOrigin: true },
      "/healthz": "http://localhost:8000",
      "/agents": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
    rollupOptions: {
      output: {
        manualChunks: { three: ["three"] },
      },
    },
  },
});

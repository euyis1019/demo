import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { HBM_DEMO_FLASK_PORT, HBM_DEMO_VITE_PORT } from "./src/constants/ports";

/** HBM Demo dev server — API proxied to Flask (PLAN2 F0-2 / F6). */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget =
    env.VITE_API_PROXY_TARGET ??
    `http://127.0.0.1:${HBM_DEMO_FLASK_PORT}`;

  return {
    plugins: [react()],
    server: {
      port: Number(env.VITE_PORT ?? HBM_DEMO_VITE_PORT),
      strictPort: true,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
          ws: true,
        },
      },
    },
  };
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** HBM Demo dev server — API proxied to Flask (PLAN2 F0-2). */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
      },
    },
  },
});

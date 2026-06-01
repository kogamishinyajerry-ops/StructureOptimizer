import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Node global, declared locally to avoid a hard dependency on @types/node.
declare const process: { env: Record<string, string | undefined> };

// Dev server proxies API + WebSocket to the FastAPI backend, so the frontend
// uses same-origin relative URLs (/api/...) in both dev and prod. Target + port
// default to :8000 / 5173 but can be overridden (e.g. VITE_API_TARGET=
// http://127.0.0.1:8201 and `vite --port 5174`) when those ports are taken.
const API_TARGET = process.env.VITE_API_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
        ws: true,
      },
    },
  },
});

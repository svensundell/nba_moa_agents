import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local dev default: 127.0.0.1 avoids macOS localhost → ::1 hitting another
// process on :8000 (e.g. an old Docker container). Override for Docker dev:
//   API_PROXY_TARGET=http://backend:8000 npm run dev
const apiProxyTarget = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },
});

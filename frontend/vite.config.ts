import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development the Vite dev server proxies API and WebSocket traffic to
// the local FastAPI backend so the UI can be tested with a single `npm run dev`.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5219,
    proxy: {
      "/api": { target: "http://127.0.0.1:8760", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8760", ws: true },
    },
  },
  build: {
    outDir: "dist",
  },
});

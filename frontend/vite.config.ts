import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Match long LLM request times (see frontend/nginx.conf proxy_read_timeout).
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        timeout: 900_000,
        proxyTimeout: 900_000,
      },
    },
  },
});

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Locally the API runs on 8001. Inside Docker (step 5) the web service sets
// API_PROXY_TARGET=http://api:8000 and WEB_PORT=5173. Neither name starts with VITE_,
// because Vite copies VITE_* variables into the code sent to the browser.
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8001";
const port = Number(process.env.WEB_PORT ?? 5174);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port,
    strictPort: true,
    proxy: {
      "/api": {
        target: apiTarget,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});

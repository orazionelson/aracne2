import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    proxy: {
      "/api": {
        // Inside Docker the frontend container reaches the backend via its
        // service name on the shared network, not via localhost.
        target: "http://backend:8000",
        changeOrigin: true,
      },
      // SEO endpoints live at /api/v1 on the backend but must be served
      // from the site root for crawlers. In production nginx rewrites
      // these paths; in dev the Vite proxy mirrors that rewrite.
      "/robots.txt": {
        target: "http://backend:8000",
        changeOrigin: true,
        rewrite: (path) => `/api/v1${path}`,
      },
      "^/sitemap(-[a-z-]+)?\\.xml$": {
        target: "http://backend:8000",
        changeOrigin: true,
        rewrite: (path) => `/api/v1${path}`,
      },
    },
  },
  build: {
    sourcemap: true,
    outDir: "dist",
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["src/tests/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      include: ["src/**/*.{ts,vue}"],
      exclude: ["src/tests/**"],
    },
  },
});

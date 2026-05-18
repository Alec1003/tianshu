/// <reference types="vitest" />
/// <reference types="vite/client" />
import fs from "node:fs";
import path from "node:path";
import { defineConfig, type Plugin } from "vite";
import svgr from "vite-plugin-svgr";
import tsconfigPaths from "vite-tsconfig-paths";
import react from "@vitejs/plugin-react";
import cesium from "vite-plugin-cesium";

// Cesium 1.121+ split into @cesium/engine + @cesium/widgets monorepo packages.
// vite-plugin-cesium@1.2.x still serves the legacy node_modules/cesium/Build/CesiumUnminified
// tree which is missing newer worker entries like incrementallyBuildTerrainPicker.js.
// This plugin overlays @cesium/engine/Build/{Workers,ThirdParty} ahead of the default middleware.
function cesiumEngineOverlay(): Plugin {
  const overlays: Array<{ prefix: string; root: string }> = [
    {
      prefix: "/cesium/Workers/",
      root: path.resolve(__dirname, "node_modules/@cesium/engine/Build/Workers"),
    },
    {
      prefix: "/cesium/ThirdParty/",
      root: path.resolve(__dirname, "node_modules/@cesium/engine/Build/ThirdParty"),
    },
  ];
  const mimeByExt: Record<string, string> = {
    ".js": "application/javascript; charset=UTF-8",
    ".mjs": "application/javascript; charset=UTF-8",
    ".json": "application/json; charset=UTF-8",
    ".wasm": "application/wasm",
    ".css": "text/css; charset=UTF-8",
  };
  return {
    name: "cesium-engine-overlay",
    enforce: "pre",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url) return next();
        const urlPath = req.url.split("?")[0];
        const overlay = overlays.find((o) => urlPath.startsWith(o.prefix));
        if (!overlay) return next();
        const rel = urlPath.slice(overlay.prefix.length);
        const fp = path.join(overlay.root, rel);
        if (!fp.startsWith(overlay.root)) return next();
        if (!fs.existsSync(fp) || !fs.statSync(fp).isFile()) return next();
        const ext = path.extname(fp).toLowerCase();
        res.setHeader("Content-Type", mimeByExt[ext] ?? "application/octet-stream");
        res.setHeader("Access-Control-Allow-Origin", "*");
        fs.createReadStream(fp).pipe(res);
      });
    },
  };
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), svgr(), tsconfigPaths(), cesiumEngineOverlay(), cesium()],
  server: {
    // Docker bind-mounted volumes lose inotify events on Windows host;
    // polling makes HMR reliable at small CPU cost.
    watch: { usePolling: true, interval: 300 },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/testing/setup.ts", // Global setup file
    include: ["src/**/*.spec.{js,jsx,ts,tsx}"], // Matches test files
  },
});

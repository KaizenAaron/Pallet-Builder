import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // three.js lives in the lazily loaded 3D-viewer chunk (~510 kB, ~130 kB gzipped)
  build: { chunkSizeWarningLimit: 700 },
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});

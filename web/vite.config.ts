import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// AGENTBOX_API_URL points the dev proxy at the running agentbox container.
// Defaults to localhost so `npm run dev` works outside Docker too.
const API_TARGET = process.env.AGENTBOX_API_URL || 'http://localhost:8765';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: path.resolve(__dirname, '../src/agentbox/ui/static/dist'),
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 700,
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    // Allow importing shared assets from the package (e.g. src/agentbox/ui/assets/logo.svg).
    fs: { allow: [path.resolve(__dirname, '..')] },
    watch: {
      // Polling is more reliable across docker bind mounts on Linux.
      usePolling: true,
      interval: 300,
    },
    hmr: {
      // The browser connects to the host-published port, not the container.
      // Override with VITE_HMR_HOST/PORT if the published port differs.
      host: process.env.VITE_HMR_HOST || 'localhost',
      port: Number(process.env.VITE_HMR_PORT || 5173),
    },
    proxy: {
      '/api': { target: API_TARGET, ws: true, changeOrigin: true },
      '/health': API_TARGET,
    },
  },
});

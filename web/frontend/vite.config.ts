import { defineConfig } from 'vite';
import solid from 'vite-plugin-solid';
import { resolve } from 'node:path';

const staticOut = resolve(__dirname, '../../src/jav_downloader/web/static');

export default defineConfig({
  plugins: [solid()],
  base: '/',
  build: {
    outDir: staticOut,
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
      },
    },
  },
});

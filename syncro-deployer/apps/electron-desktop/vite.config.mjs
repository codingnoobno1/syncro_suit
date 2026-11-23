import { defineConfig } from 'vite';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: path.resolve(__dirname, 'renderer'),
  base: './',
  build: {
    outDir: path.resolve(__dirname, 'dist'),
    emptyOutDir: true,
    target: 'es2022',
  },
  server: {
    port: 5175,
    host: '0.0.0.0',
    proxy: {
      '/api': 'http://127.0.0.1:8080',
      '/mcp': 'http://127.0.0.1:8080',
      '/metrics': 'http://127.0.0.1:8080',
      '/ws': {
        target: 'ws://127.0.0.1:8080',
        ws: true,
      },
    },
  },
});

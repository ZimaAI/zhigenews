import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';
// VS Code tasks point at the local debugger; ordinary dev/preview use the container API.
const apiTarget = process.env.ZHIGENEWS_API_TARGET || 'http://127.0.0.1:18000';
export default defineConfig({
  plugins: [vue()],
  publicDir: fileURLToPath(new URL('../../packages/ui/src/assets', import.meta.url)),
  resolve: { alias: { '@ui': fileURLToPath(new URL('../../packages/ui/src', import.meta.url)), '@api': fileURLToPath(new URL('../../packages/api-client/src', import.meta.url)) } },
  server: { port: 5174, strictPort: true, proxy: { '/api': { target: apiTarget, changeOrigin: false } } },
  preview: { port: 5174, strictPort: true, proxy: { '/api': { target: apiTarget, changeOrigin: false } } },
});

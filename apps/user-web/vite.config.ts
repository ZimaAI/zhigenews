import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';
export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@ui': fileURLToPath(new URL('../../packages/ui/src', import.meta.url)), '@api': fileURLToPath(new URL('../../packages/api-client/src', import.meta.url)) } },
  server: { port: 5173, strictPort: true, proxy: { '/api': { target: 'http://127.0.0.1:18000', changeOrigin: false } } },
  preview: { port: 5173, strictPort: true, proxy: { '/api': { target: 'http://127.0.0.1:18000', changeOrigin: false } } },
});

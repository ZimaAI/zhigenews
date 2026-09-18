import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';
export default defineConfig({
  plugins: [vue()],
  define: { 'import.meta.env.VITE_APP_KIND': JSON.stringify('admin') },
  resolve: { alias: { '@shared': fileURLToPath(new URL('../shared', import.meta.url)) } },
  server: { host: '127.0.0.1', port: 5174, strictPort: true, proxy: { '/__demo': { target: 'http://127.0.0.1:5173', changeOrigin: true } }, fs: { allow: [fileURLToPath(new URL('..', import.meta.url))] } },
});

import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { anonymousDemoServer } from '../shared/demo-server';
import { fileURLToPath, URL } from 'node:url';
export default defineConfig({
  plugins: [vue(), anonymousDemoServer(fileURLToPath(new URL('../.demo/anonymous.json', import.meta.url)))],
  define: { 'import.meta.env.VITE_APP_KIND': JSON.stringify('user') },
  resolve: { alias: { '@shared': fileURLToPath(new URL('../shared', import.meta.url)) } },
  server: { host: '127.0.0.1', port: 5173, strictPort: true, fs: { allow: [fileURLToPath(new URL('..', import.meta.url))] } },
});

import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    port: 2173,
    proxy: {
      // ws:true so the scan WebSocket (/api/scan/{id}/ws) proxies too,
      // letting the client use a same-origin URL (works in dev + behind nginx).
      '/api': { target: 'http://localhost:2801', ws: true },
      '/auth': 'http://localhost:2801',
    },
  },
});

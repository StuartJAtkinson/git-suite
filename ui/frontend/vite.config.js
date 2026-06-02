import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    port: 2173,
    proxy: {
      '/api': 'http://localhost:2800',
      '/auth': 'http://localhost:2800',
    },
  },
});

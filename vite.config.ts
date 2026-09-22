import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  root: 'ui',
  build: { outDir: '../dist', emptyOutDir: true },
  server: {
    host: '127.0.0.1', port: Number(process.env.STONIC_UI_PORT || 5173), strictPort: true,
    proxy: {
      '/api/': {
        target: `http://127.0.0.1:${process.env.STONIC_PORT || '8765'}`,
        headers: { 'X-Stonic-Token': process.env.STONIC_API_TOKEN || '' },
      },
    },
  },
});

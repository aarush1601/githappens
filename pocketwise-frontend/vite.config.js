import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// /api requests go to the Python backend (PennyWise coach), so no CORS setup is needed.
const backend = process.env.PENNYWISE_API || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': { target: backend, changeOrigin: true } } },
  preview: { proxy: { '/api': { target: backend, changeOrigin: true } } },
});

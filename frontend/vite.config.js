import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// Forward app APIs to FastAPI while Supabase Auth uses the public Supabase URL.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/complaints': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      // Keep /warden and /warden/* frontend URLs in Vite's SPA fallback; only
      // forward the concrete Warden API endpoints to FastAPI.
      '^/warden/(dashboard|workers|reports)(?:/|$)': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      // Browser navigation needs the SPA shell; JSON fetches still go to FastAPI.
        bypass: req => /text\/html/i.test(req.headers.accept || '') ? req.url : undefined,
      },
      '/auth': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/tasks': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/alerts': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/digest': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// Dev proxy: the student UI calls same-origin /complaints; Vite forwards it to
// the FastAPI backend, so no CORS setup and no VITE_API_BASE_URL are needed in
// development. Set VITE_API_BASE_URL to talk to a different backend origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/complaints': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})

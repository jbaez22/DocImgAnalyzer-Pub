import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],
    server: {
      // In dev, proxy /api/* to the real API endpoint so no CORS preflight occurs.
      // The browser only sees localhost:5173 → localhost:5173 (same-origin).
      // Controlled by DEV_API_PROXY_TARGET in .env.development — no hardcoded URLs.
      proxy: {
        '/api': {
          target: env.DEV_API_PROXY_TARGET,
          changeOrigin: true,
        },
      },
    },
  }
})

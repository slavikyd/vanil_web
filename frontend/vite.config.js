import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    strictPort: false,
    proxy: {
      '^/api/': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '^/login$': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '^/logout$': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '^/add-to-order': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '^/place_order': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '^/orders': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '^/admin': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: true
  }
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Proxy a backend:8002 en dev. Basket vive en VPS2 (212.227.50.152) junto a
// futbol (8000/8001); 8002 esta libre alli. (Tenis/TT usan 8002/8003 en VPS1).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5175,
    proxy: {
      '/graphql': 'http://127.0.0.1:8002',
      '/api': 'http://127.0.0.1:8002',
      '/status': 'http://127.0.0.1:8002',
    },
  },
})

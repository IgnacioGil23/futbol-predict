import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// base relativa: el sitio se publica en un subdirectorio de GitHub Pages (/<repo>/).
export default defineConfig({
  base: './',
  plugins: [react()],
  build: { chunkSizeWarningLimit: 700 },
  test: { environment: 'node' },
})

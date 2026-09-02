import { defineConfig } from 'vite'
import { resolve } from 'node:path'

export default defineConfig({
  publicDir: resolve(process.cwd(), '../web/public'),
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})

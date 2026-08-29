import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const rayongSourceCompatibility: Plugin = {
  name: 'rayong-source-compatibility',
  enforce: 'pre',
  transform(code, id) {
    if (!id.endsWith('/src/App.tsx')) return null
    return code
      .replace(/\bLayers3\b/g, 'Layers')
      .replace(/\bMapPinned\b/g, 'MapPin')
      .replace(
        'return new URL(path, document.baseURI).toString();',
        `return new URL(
    path,
    window.location.pathname.includes('/web/published/')
      ? new URL('../public/', document.baseURI)
      : document.baseURI,
  ).toString();`,
      )
  },
}

export default defineConfig({
  plugins: [rayongSourceCompatibility, react()],
  // Relative bundle assets support local tests and branch-hosted static publishing.
  base: './',
})

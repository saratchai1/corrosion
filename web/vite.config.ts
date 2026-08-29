import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const lucideLegacyAliases: Plugin = {
  name: 'lucide-legacy-aliases',
  enforce: 'pre',
  transform(code, id) {
    if (!id.endsWith('/src/App.tsx')) return null
    return code
      .replace(/\bLayers3\b/g, 'Layers')
      .replace(/\bMapPinned\b/g, 'MapPin')
  },
}

export default defineConfig({
  plugins: [lucideLegacyAliases, react()],
  // Relative assets work on both GitHub Pages (/corrosion/) and Vercel (/).
  base: './',
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'node:path'

export default defineConfig({
  plugins: [
    react(),
    // Precaches the app shell, fonts, rules and sources (they are bundled), so the result works with no internet.
    // /api is never cached or intercepted: the explanation is online-only by design.
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
      manifest: {
        name: 'Baby Watch',
        short_name: 'Baby Watch',
        description: 'Pregnancy danger-sign check. Know when to get care. Works without internet.',
        theme_color: '#1D4FD7',
        background_color: '#FFFFFF',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        scope: '/',
        icons: [
          { src: 'pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'pwa-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2,webmanifest}'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        cleanupOutdatedCaches: true,
      },
    }),
  ],
  resolve: { alias: { '@rules': path.resolve(import.meta.dirname, '../rules') } },
  server: { fs: { allow: ['..'] }, proxy: { '/api': 'http://127.0.0.1:8000' } },
})

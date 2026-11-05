import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * Group third-party code into stable vendor chunks so that route chunks stay
 * small and vendor code is cached independently of app code.
 */
function manualChunks(id) {
  if (!id.includes('node_modules')) {
    // Locale JSON is code-split per language by the dynamic imports in src/i18n.
    return undefined
  }
  // vue-flow and its own runtime deps (d3 zoom/selection, vueuse)
  if (id.includes('@vue-flow/') || id.includes('/d3-') || id.includes('/@vueuse/')) {
    return 'vendor-vueflow'
  }
  if (id.includes('/markdown-it') || id.includes('/linkify-it') || id.includes('/mdurl') ||
      id.includes('/uc.micro') || id.includes('/entities/') || id.includes('/punycode')) {
    return 'vendor-markdown'
  }
  if (id.includes('/js-yaml')) return 'vendor-yaml'
  if (id.includes('/vue-i18n') || id.includes('/@intlify/')) return 'vendor-i18n'
  if (id.includes('/vue-router') || id.includes('/@vue/') || id.includes('/vue/')) {
    return 'vendor-vue'
  }
  return undefined
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_API_BASE_URL || 'http://localhost:6400'

  return {
    plugins: [vue()],
    // Playwright specs live in e2e/ and run with `npm run e2e`, not Vitest
    test: { exclude: ['e2e/**', 'node_modules/**', 'dist/**'] },
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks,
        },
      },
    },
    server: {
      host: true,
      proxy: {
        '/api': {
          target: target,
          changeOrigin: true,
        },
        '/ws': {
          target: target,
          ws: true,
          changeOrigin: true,
        }
      }
    }
  }
})

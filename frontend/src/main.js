import { createApp } from 'vue'
import '@/assets/styles/main.css'
import App from './App.vue'
import router from '@/router'
import i18n, { initI18n } from '@/i18n'
import '@/assets/styles/fonts.css'
import '@/assets/styles/markdown.css'
import '@/assets/styles/heroSprite.css'

// Mount once the active locale's messages are in (one small lazy chunk), so the
// first paint never flashes raw translation keys.
initI18n()
  .catch((error) => console.error('Failed to load locale messages:', error))
  .finally(() => createApp(App).use(router).use(i18n).mount('#app'))

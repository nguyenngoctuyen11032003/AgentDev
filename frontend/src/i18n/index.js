import { createI18n } from 'vue-i18n'
import en from './locales/en.json'
import zh from './locales/zh.json'
import vi from './locales/vi.json'

export const SUPPORTED_LOCALES = ['vi', 'en', 'zh']
export const DEFAULT_LOCALE = 'vi'

const CONFIG_KEY = 'agent_config_settings'
let savedLanguage = DEFAULT_LOCALE
try {
  const stored = localStorage.getItem(CONFIG_KEY)
  if (stored) {
    const lang = JSON.parse(stored).LANGUAGE
    if (SUPPORTED_LOCALES.includes(lang)) savedLanguage = lang
  }
} catch {
  // Corrupt or inaccessible storage: keep the default locale
}

const i18n = createI18n({
  locale: savedLanguage,
  fallbackLocale: 'en',
  messages: {
    vi,
    en,
    zh
  },
  legacy: false,
  globalInjection: true
})

export default i18n

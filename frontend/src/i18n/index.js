import { createI18n } from 'vue-i18n'

export const SUPPORTED_LOCALES = ['vi', 'en', 'zh']
export const DEFAULT_LOCALE = 'vi'

// One lazy chunk per language: only the active locale is downloaded and parsed
// at startup (each file is ~55 KB of JS), the others load when selected.
const loaders = {
  vi: () => import('./locales/vi.json'),
  en: () => import('./locales/en.json'),
  zh: () => import('./locales/zh.json')
}

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
  messages: {},
  legacy: false,
  globalInjection: true,
  // Missing keys are expected while the 'en' fallback is still loading.
  missingWarn: false,
  fallbackWarn: false
})

const pending = new Map()

/** Download a locale's messages once and register them. */
export function loadLocaleMessages(lang) {
  if (!SUPPORTED_LOCALES.includes(lang)) return Promise.resolve()
  if (i18n.global.availableLocales.includes(lang)) return Promise.resolve()
  if (!pending.has(lang)) {
    pending.set(
      lang,
      loaders[lang]().then((mod) => {
        i18n.global.setLocaleMessage(lang, mod.default)
      })
    )
  }
  return pending.get(lang)
}

/** Switch the UI language, loading its messages first. */
export async function setLocale(lang) {
  await loadLocaleMessages(lang)
  i18n.global.locale.value = lang
}

/**
 * Load what the first render needs. The fallback ('en') only matters for keys
 * missing from the active locale, so it is fetched in the background.
 */
export function initI18n() {
  const ready = loadLocaleMessages(savedLanguage)
  if (savedLanguage !== 'en') {
    ready.then(() => loadLocaleMessages('en')).catch(() => {})
  }
  return ready
}

export default i18n

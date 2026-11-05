import { reactive, watch } from 'vue'
import { SUPPORTED_LOCALES, DEFAULT_LOCALE } from '@/i18n/index.js'

const CONFIG_KEY = 'agent_config_settings'

export const THEMES = ['dark', 'light', 'system']

const defaultSettings = {
    AUTO_SHOW_ADVANCED: false,
    ENABLE_HELP_TOOLTIPS: true,
    LANGUAGE: 'vi',
    THEME: 'dark'
}

// Initialize state from localStorage
let initialState = { ...defaultSettings }
try {
    const stored = localStorage.getItem(CONFIG_KEY)
    if (stored) initialState = { ...defaultSettings, ...JSON.parse(stored) }
} catch {
    // Corrupt or inaccessible storage: fall back to defaults
}
// Drop the retired AUTO_EXPAND_MESSAGES flag a previous version may have saved
delete initialState.AUTO_EXPAND_MESSAGES
if (!SUPPORTED_LOCALES.includes(initialState.LANGUAGE)) {
    initialState.LANGUAGE = DEFAULT_LOCALE
}
if (!THEMES.includes(initialState.THEME)) {
    initialState.THEME = defaultSettings.THEME
}

export const configStore = reactive(initialState)

// Watch for changes and save to localStorage
watch(configStore, (newVal) => {
    localStorage.setItem(CONFIG_KEY, JSON.stringify(newVal))
}, { deep: true })

// ---------------------------------------------------------------------------
// Theme handling
// ---------------------------------------------------------------------------
const systemDark = typeof window !== 'undefined' && window.matchMedia
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null

/** Resolve 'system' to the concrete theme the OS is asking for. */
export function resolveTheme(theme) {
    if (theme === 'system') return systemDark && systemDark.matches ? 'dark' : 'light'
    return theme === 'light' ? 'light' : 'dark'
}

let transitionTimer = null

/**
 * Apply a theme to <html>. Pass 'dark' | 'light' | 'system'.
 * Used both for the saved setting and for live preview inside the settings modal.
 */
export function applyTheme(theme, { animate = true } = {}) {
    const root = document.documentElement
    const resolved = resolveTheme(theme)
    if (root.dataset.theme === resolved) return
    if (animate) {
        root.classList.add('theme-transition')
        clearTimeout(transitionTimer)
        transitionTimer = setTimeout(() => root.classList.remove('theme-transition'), 350)
    }
    root.dataset.theme = resolved
}

applyTheme(configStore.THEME, { animate: false })
watch(() => configStore.THEME, (t) => applyTheme(t))
if (systemDark) {
    const onChange = () => { if (configStore.THEME === 'system') applyTheme('system') }
    if (systemDark.addEventListener) systemDark.addEventListener('change', onChange)
    else systemDark.addListener(onChange)
}

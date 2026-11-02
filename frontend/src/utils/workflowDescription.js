import i18n from '@/i18n'

/**
 * Return the workflow description in the active UI language.
 * Falls back to the description stored in the YAML file when no translation exists.
 * Reads the reactive locale, so templates calling this re-render on language change.
 */
export function localizedWorkflowDescription(name, fallback = '') {
  const { t, te, locale } = i18n.global
  const key = `workflow_descriptions.${String(name ?? '').replace(/\.ya?ml$/i, '')}`
  // Touch locale.value so Vue tracks it as a dependency
  return locale.value && te(key) ? t(key) : fallback
}

import i18n from '@/i18n'

const t = (...args) => i18n.global.t(...args)

export const isListField = (field) => {
  return field.type && field.type.includes('list[')
}

export const hasChildRoutes = (field) => {
  return Array.isArray(field?.childRoutes) && field.childRoutes.length > 0
}

export const isInlineConfigField = (field) => {
  return hasChildRoutes(field) && !isListField(field)
}

export const getSchemaFields = (modal) => {
  return modal?.schema?.fields || []
}

export const getDisplayFields = (modal) => {
  return getSchemaFields(modal)
}

export const determineRouteControllerField = (modal, field) => {
  if (!hasChildRoutes(field)) {
    return null
  }
  const schemaFields = getSchemaFields(modal)
  const preferredTypeField = schemaFields.find(entry => entry.name === 'type')
  if (preferredTypeField) {
    return preferredTypeField.name
  }
  const routeValues = field.childRoutes
    .map(route => route?.childKey?.value)
    .filter(value => value !== undefined && value !== null)
  if (!routeValues.length) {
    const fallbackField = schemaFields.find(entry => Array.isArray(entry.enum) && entry.enum.length)
    return fallbackField ? fallbackField.name : null
  }
  const matchingEnumField = schemaFields.find(
    entry => Array.isArray(entry.enum) && routeValues.every(value => entry.enum.includes(value))
  )
  return matchingEnumField ? matchingEnumField.name : null
}

export const getActiveChildRoute = (modal, field) => {
  if (!hasChildRoutes(field)) {
    return null
  }
  const routes = field.childRoutes || []
  if (!routes.length) {
    return null
  }
  const controllerFieldName = determineRouteControllerField(modal, field)
  if (!controllerFieldName) {
    return routes[0]
  }
  const controllerValue = modal.formData?.[controllerFieldName]
  return routes.find(route => {
    const keyValue = route?.childKey?.value
    if (keyValue === undefined || keyValue === null) {
      return controllerValue === undefined || controllerValue === null || controllerValue === ''
    }
    return keyValue === controllerValue
  }) || null
}

export const canOpenConditionalChildModal = (modal, field) => {
  return Boolean(getActiveChildRoute(modal, field))
}

export const getConditionalChildKeyValue = (modal, field) => {
  const route = getActiveChildRoute(modal, field)
  if (route?.childKey?.value) {
    return route.childKey.value
  }
  if (field.childKey?.value) {
    return field.childKey.value
  }
  return null
}

export const isFieldVisible = (modal, field) => {
  if (!field?.advance) {
    return true
  }
  return Boolean(modal?.showAdvanced)
}

export const childNodeButtonLabel = (modal, field) => {
  if (isListField(field)) {
    return t('dynamic_form_field.add_entry')
  }
  return modal.formData[field.name]
    ? t('dynamic_form_field.edit_child', { child: field.childNode })
    : t('dynamic_form_field.configure_child', { child: field.childNode })
}

export const conditionalChildButtonLabel = (modal, field) => {
  if (!canOpenConditionalChildModal(modal, field)) {
    return t('dynamic_form_field.configure')
  }
  const childNodeName = getConditionalChildKeyValue(modal, field)
  return modal.formData[field.name]
    ? t('dynamic_form_field.edit_child', { child: childNodeName })
    : t('dynamic_form_field.configure_child', { child: childNodeName })
}

// Stable key for a backend-provided English text (djb2 -> base36). The same function is used by the
// script that generates the schema_desc_text translations, so keep both in sync if it ever changes.
// Results are memoized: the same description/label strings are hashed for every field render
// (labels, tooltips, summaries), and descriptions can be long.
const MAX_KEY_CACHE = 2000
const textKeyCache = new Map()
const slugKeyCache = new Map()

const memoKey = (cache, text, compute) => {
  const str = String(text)
  const cached = cache.get(str)
  if (cached !== undefined) return cached
  const result = compute(str)
  if (cache.size >= MAX_KEY_CACHE) cache.clear()
  cache.set(str, result)
  return result
}

export const textKey = (text) => memoKey(textKeyCache, text, (str) => {
  let h = 5381
  for (const c of str) h = ((h * 33) ^ c.codePointAt(0)) >>> 0
  return 'h' + h.toString(36)
})

const slugKey = (text) => memoKey(slugKeyCache, text, (str) =>
  str.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
)

// Return the translation for the first key that exists in the current locale, else null.
const firstTranslated = (keys) => {
  for (const key of keys) {
    if (key && i18n.global.te(key)) return t(key)
  }
  return null
}

// Label/description resolution for backend-provided schema fields. Most specific translation wins:
// 1. schema_display.<slug(displayName)> / schema_desc_text.<textKey(description)>  (per backend text)
// 2. schema.<name> / schema_desc.<name>                                           (generic, per field name)
// 3. backend displayName/description, then the raw field name.
export const getFieldLabel = (field) => {
  const name = field?.name
  const display = field?.displayName
  const slug = display ? slugKey(display) : ''
  return firstTranslated([slug && `schema_display.${slug}`, name && `schema.${name}`]) ??
    (display || name || '')
}

export const getFieldDescription = (field) => {
  const name = field?.name
  const desc = field?.description
  return firstTranslated([desc && `schema_desc_text.${textKey(desc)}`, name && `schema_desc.${name}`]) ??
    (desc || '')
}

// Enum option labels can be localized with schema_enum.<field>.<value>;
// otherwise fall back to the backend label, then the raw value.
const SAFE_KEY_SEGMENT = /^[A-Za-z0-9_-]+$/

export const getEnumOptionLabel = (field, option) => {
  const value = typeof option === 'string' ? option : option?.value
  const name = field?.name
  if (
    typeof value === 'string' &&
    typeof name === 'string' &&
    SAFE_KEY_SEGMENT.test(value) &&
    SAFE_KEY_SEGMENT.test(name)
  ) {
    const key = `schema_enum.${name}.${value}`
    if (i18n.global.te(key)) {
      return t(key)
    }
  }
  if (typeof option === 'string') {
    return option
  }
  return option?.label ?? (value ?? '')
}

// Enum option descriptions. The same field/value pair can carry different descriptions in different
// config classes, so the exact-text key wins: schema_desc_text.<textKey(description)>,
// then schema_enum_desc.<field>.<value>, else the backend description.
export const getEnumOptionDescription = (field, option) => {
  if (!option || typeof option === 'string') return ''
  const value = option.value
  const name = field?.name
  const desc = option.description
  const safe = typeof value === 'string' && typeof name === 'string' &&
    SAFE_KEY_SEGMENT.test(value) && SAFE_KEY_SEGMENT.test(name)
  return firstTranslated([
    desc && `schema_desc_text.${textKey(desc)}`,
    safe && `schema_enum_desc.${name}.${value}`
  ]) ?? (desc || '')
}

// Display helpers for the account details returned by GET /api/connections/:id/account.

const USAGE_KEYS = {
  session: 'connections.usage_session',
  weekly: 'connections.usage_weekly',
  weekly_all: 'connections.usage_weekly',
  monthly: 'connections.usage_monthly'
}

export function usageLabel(t, window) {
  const key = USAGE_KEYS[window.kind]
  if (key) return t(key)
  // Scoped limits such as "weekly_opus" -> "Weekly · Opus"
  const [period, ...scope] = String(window.kind).split('_')
  const base = USAGE_KEYS[period] ? t(USAGE_KEYS[period]) : period
  return scope.length ? `${base} · ${scope.join(' ')}` : base
}

export function usageLevel(percent) {
  if (percent >= 90) return 'danger'
  if (percent >= 70) return 'warn'
  return 'ok'
}

const sameDay = (a, b) => a.toDateString() === b.toDateString()

// "1:10 AM" for today, "Sun, Nov 8, 7:00 AM" otherwise, in the UI language.
export function formatReset(iso, locale) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const time = { hour: 'numeric', minute: '2-digit' }
  const options = sameDay(date, new Date()) ? time : { weekday: 'short', month: 'short', day: 'numeric', ...time }
  return new Intl.DateTimeFormat(locale, options).format(date)
}

export function formatDateTime(iso, locale) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

// Top-tier models get a highlighted chip.
export const isPremiumModel = (id) => /fable/i.test(id)

// Account models (objects) or catalog/test models (strings), normalised to {id, name, primary}.
export function normalizeModels(list) {
  return (list || []).map((model) =>
    typeof model === 'string' ? { id: model, name: model, primary: true } : model
  )
}

export const accountName = (account) => account?.displayName || account?.email || ''

// Finishing a platform fix (docs/adr/0009-platform-fix-loop.md): pure helpers for the Lab "platform fixes" section.
// The server sends stable codes (gates, statuses, blockers, actions, next steps, errors); the UI translates them.

/** Verify gates in run order (backend platform_fix_finish.GATES). */
export const GATE_CODES = [
  'forbidden_untouched',
  'backend_sync',
  'backend_tests',
  'frontend_install',
  'frontend_tests',
  'frontend_lint',
  'frontend_build',
  'frontend_i18n'
]

/** Merge blockers in the order the server checks them. */
export const BLOCKER_CODES = [
  'verify_required',
  'verify_stale',
  'forbidden_touched',
  'brief_committed',
  'ai_attribution',
  'main_dirty',
  'not_on_main',
  'nothing_to_merge'
]

export const GATE_STATUSES = ['pending', 'running', 'passed', 'failed', 'timeout', 'skipped', 'cancelled']

const TONES = { passed: 'ok', skipped: 'muted', pending: 'muted', running: 'live', failed: 'bad', timeout: 'bad', cancelled: 'warn' }

/** Visual tone of a gate / verify status: ok | bad | warn | live | muted (unknown statuses are muted). */
export const statusTone = (status) => TONES[status] || 'muted'

export const list = (value) => (Array.isArray(value) ? value : [])

/** A verify is running on the server: poll the item and offer "cancel" instead of "verify again". */
export const isVerifying = (item) => item?.verify?.status === 'running'

/** Merge is offered only when the server says so and no verify is in flight. */
export const canMerge = (item) => !!item && item.mergeable === true && !isVerifying(item) && list(item.blockers).length === 0

/** Known blocker codes of an item, in server order, unknown codes kept at the end (shown with a generic text). */
export function blockersOf(item) {
  const codes = list(item?.blockers).map(String)
  const known = BLOCKER_CODES.filter((code) => codes.includes(code))
  return [...known, ...codes.filter((code) => !BLOCKER_CODES.includes(code))]
}

/** Gates of the last verify, in run order; gates the server added later keep their place at the end. */
export function gatesOf(item) {
  const gates = list(item?.verify?.gates)
  const order = (g) => {
    const index = GATE_CODES.indexOf(g?.code)
    return index === -1 ? GATE_CODES.length : index
  }
  return [...gates].sort((a, b) => order(a) - order(b))
}

export const SHORT_SHA = 10
export const shortSha = (sha) => (sha ? String(sha).slice(0, SHORT_SHA) : '')

/** Params for vue-i18n: shas shortened, arrays joined, so every message reads well in any locale. */
export function i18nParams(params) {
  const out = {}
  for (const [key, value] of Object.entries(params && typeof params === 'object' ? params : {})) {
    if (Array.isArray(value)) out[key] = value.map((v) => (key === 'commits' ? shortSha(v) : String(v))).join(', ')
    else if (['commit', 'head', 'merge_commit'].includes(key) && value) out[key] = shortSha(value)
    else out[key] = value
  }
  return out
}

/** Stable error code ("lab_bad_password" -> "bad_password"). */
export const errorCodeOf = (error) => String(error?.code || error?.error_code || '').replace(/^lab_/, '')

/** i18n keys tried for an error code, most specific first. */
export const errorKeys = (code) => (code ? [`lab.platform_fixes.errors.${code}`, `lab.platform_fix.errors.${code}`] : [])

/** Polling delay while a verify runs: 1.5 s, growing x1.5 per poll, capped at 10 s. */
export const pollDelay = (attempt) => Math.min(10_000, Math.round(1500 * 1.5 ** Math.max(0, attempt)))

/** Files a merge refusal or conflict names (params.files) or commits (params.commits). */
export const refusalItems = (error) => [...list(error?.params?.files), ...list(error?.params?.commits).map(shortSha)]

/**
 * Readable text of a platform-fix API error: a merge refused by a blocker reads as that blocker's sentence + fix
 * (and the files / commits it names); other codes use lab.platform_fixes.errors.<code>, then
 * lab.platform_fix.errors.<code>, then the generic Lab error text (`fallback`).
 */
export function platformFixErrorText(error, { t, te, fallback }) {
  const code = errorCodeOf(error)
  if (BLOCKER_CODES.includes(code)) {
    const base = 'lab.platform_fixes.blockers'
    let text = t('lab.platform_fixes.errors.blocked', { reason: t(`${base}.${code}.text`), fix: t(`${base}.${code}.fix`) })
    const items = refusalItems(error)
    if (items.length) text += ` ${t('lab.platform_fixes.errors.blocked_items', { items: items.join(', ') })}`
    return text
  }
  const key = errorKeys(code).find((k) => te(k))
  if (key) return t(key, i18nParams(error?.params))
  return fallback(error)
}

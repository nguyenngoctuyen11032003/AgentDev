import i18n from '@/i18n'

// Backend errors are English plain text (HTTPException detail, ConfigError, CliProviderError,
// SecurityError, run error events). These rules recognise the common ones and map them to
// `errors.backend.*` keys so the UI can show them in the user's language. The original text is
// never lost: callers keep it as the technical detail.
// Order matters: the first matching rule wins, so specific rules come before generic ones.
const RULES = [
  { key: 'account_exhausted', re: /reached its usage limit and no other\s+signed-in account/i },
  { key: 'no_account', re: /no signed-in account|not signed in: sign in|has no account connection/i },
  { key: 'connection_not_found', re: /\bconnection not found\b/i },
  { key: 'unknown_vendor', re: /unknown vendor '([^']*)'/i, params: (m) => ({ vendor: m[1] }) },
  {
    key: 'cli_not_installed',
    re: /`(\w+)` CLI (?:is )?not installed|CLI for this provider is not installed/i,
    params: (m) => ({ cli: m[1] || 'CLI' })
  },
  {
    key: 'cli_not_logged_in',
    re: /`(\w+)` CLI is not logged in|\bnot logged in; run `(\w+)/i,
    params: (m) => ({ cli: m[1] || m[2] || 'CLI' })
  },
  {
    key: 'cli_timeout',
    re: /`(\w+)` CLI timed out after (\d+)\s*s/i,
    params: (m) => ({ cli: m[1], seconds: m[2] })
  },
  {
    key: 'quota',
    re: /account limit reached|usage limit|rate.?limit|quota (?:exceeded|reached)|insufficient_quota|\b429\b/i
  },
  {
    key: 'cli_failed',
    re: /`(\w+)` CLI (?:error|exited with code|returned no result)/i,
    params: (m) => ({ cli: m[1] })
  },
  { key: 'code_execution_disabled', re: /MAC_ALLOW_UNSAFE_CODE_EXECUTION/ },
  { key: 'run_in_progress', re: /a run is already in progress|\brun_in_progress\b/i },
  { key: 'workflow_exists', re: /workflow already exists/i },
  { key: 'workflow_not_found', re: /workflow(?: file)? not found/i },
  { key: 'session_not_found', re: /\bsession not found\b/i },
  { key: 'lab_run_not_found', re: /\blab run not found\b/i },
  { key: 'project_workspace_not_found', re: /project workspace not found/i },
  {
    key: 'skill_permission_denied',
    re: /permission denied[^\n]*(?:skill folder|file in use or read-only)/i
  },
  { key: 'skill_folder_failed', re: /could not update the skill folder/i },
  { key: 'invalid_yaml', re: /\binvalid[ _]yaml\b|yaml root must be a mapping/i },
  { key: 'validation_failed', re: /validation failed/i }
]

const t = (key, params) => i18n.global.t(key, params)
const te = (key) => i18n.global.te(key)

// {key, params} for a recognised backend error text, otherwise null.
export function matchBackendError(text) {
  if (typeof text !== 'string' || !text.trim()) return null
  for (const rule of RULES) {
    const match = text.match(rule.re)
    if (match) {
      return { key: `errors.backend.${rule.key}`, params: rule.params ? rule.params(match) : {} }
    }
  }
  return null
}

// Localized message for a recognised backend error text; '' when it is not recognised.
export function localizeBackendError(text) {
  const hit = matchBackendError(text)
  if (!hit || !te(hit.key)) return ''
  return t(hit.key, hit.params)
}

// Display text for a backend error: the localized message with the original text kept as the
// technical detail underneath; unrecognised text is returned unchanged.
export function localizeErrorText(text) {
  const localized = localizeBackendError(text)
  if (!localized) return text
  return `${localized}\n${t('errors.backend.technical', { detail: text.trim() })}`
}

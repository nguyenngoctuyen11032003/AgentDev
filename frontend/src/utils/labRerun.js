// Re-running a Lab job's failed scenarios after a fix: error codes and the before/after table.

/** Metrics of `rerun_compare.before/after`, in display order. A flag on one means it got worse. */
export const RERUN_METRICS = ['pass_rate', 'avg_seconds', 'cost_usd']

const KNOWN_ERRORS = new Set(['nothing_to_rerun', 'confirm_required'])

/**
 * Stable code of a rerun API error, for its translated message + fix hint:
 * the server's code when known, `not_found` (404), `network` (no HTTP answer), else `failed`.
 */
export function rerunErrorCode(error) {
  const code = error?.code || error?.error_code
  if (KNOWN_ERRORS.has(code)) return code
  if (error?.status === 404) return 'not_found'
  if (!error?.status) return 'network'
  return 'failed'
}

const num = (value) => (typeof value === 'number' && Number.isFinite(value) ? value : null)

// Cost of one run when the side carries its number of finished runs (`done`), else null.
const perRun = (side) => {
  const cost = num(side.cost_usd)
  const done = num(side.done)
  return cost !== null && done ? cost / done : null
}

/**
 * Rows of the before/after table from a job's `rerun_compare` ({before, after, flags}).
 * Cost is shown per run when both sides have `done` (as the backend's `flags.cost_usd` compares it),
 * else as job totals (`perRun: false`). Metrics missing on both sides are dropped.
 * -> [{key, before, after, worse, perRun}]
 */
export function rerunCompareRows(compare) {
  if (!compare || typeof compare !== 'object') return []
  const before = compare.before || {}
  const after = compare.after || {}
  const flags = compare.flags && typeof compare.flags === 'object' ? compare.flags : {}
  return RERUN_METRICS.map((key) => {
    if (key === 'cost_usd' && perRun(before) !== null && perRun(after) !== null) {
      return { key, before: perRun(before), after: perRun(after), worse: !!flags[key], perRun: true }
    }
    return { key, before: num(before[key]), after: num(after[key]), worse: !!flags[key], perRun: false }
  }).filter((row) => row.before !== null || row.after !== null)
}

/** "80%", "12s", "$0.024"; '—' when the value is unknown. */
export function formatRerunValue(key, value) {
  if (value === null || value === undefined) return '—'
  if (key === 'pass_rate') return `${Math.round(value * 100)}%`
  if (key === 'avg_seconds') return `${Math.round(value)}s`
  // Per-run costs are small: keep 4 digits below a cent so $0.0100 -> $0.0130 still reads as a change.
  return `$${value.toFixed(value < 0.01 ? 4 : value < 0.1 ? 3 : 2)}`
}

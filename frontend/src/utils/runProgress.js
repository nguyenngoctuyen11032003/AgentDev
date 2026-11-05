/**
 * Progress of a plain (non-team) run from its step statuses (see stepStatus).
 * Once the run completed, a step that never started was never triggered (e.g. a conditional
 * branch not taken), so it leaves the denominator. A failed step that was skipped
 * (continue_on_error) did run and still counts, which keeps the percentage below 100.
 */
export function stepProgress(statuses, outcome) {
  const counted = outcome === 'completed' ? statuses.filter((s) => s !== 'todo') : statuses
  const done = counted.filter((s) => s === 'done').length
  const total = counted.length
  return { done, total, percent: total ? Math.round((done / total) * 100) : 0 }
}

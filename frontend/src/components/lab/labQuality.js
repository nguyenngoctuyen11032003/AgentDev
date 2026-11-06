// Rubric dimensions of a Lab verdict, in the order the judge grades them (see backend lab_quality.DIMENSIONS).
export const QUALITY_DIMENSIONS = ['requirements', 'correctness', 'craft', 'verification', 'communication', 'effort_fit']
const WEAK_BELOW = 7
const POOR_BELOW = 5

const scoreOf = (value) => {
  const raw = value && typeof value === 'object' ? value.score : value
  const n = Number(raw)
  return raw === null || raw === undefined || raw === '' || Number.isNaN(n) ? null : n
}

// Rows to show: known dimensions with a score, in rubric order, each with its tone (ok / mid / low).
export function qualityRows(dimensions) {
  if (!dimensions || typeof dimensions !== 'object') return []
  const rows = []
  for (const key of QUALITY_DIMENSIONS) {
    const score = scoreOf(dimensions[key])
    if (score === null) continue
    const note = typeof dimensions[key] === 'object' ? String(dimensions[key].note || '') : ''
    rows.push({ key, score, note, tone: score < POOR_BELOW ? 'low' : score < WEAK_BELOW ? 'mid' : 'ok' })
  }
  return rows
}

// Dimensions under the "needs work" line, lowest first.
export function weakDimensions(dimensions) {
  return qualityRows(dimensions).filter((r) => r.score < WEAK_BELOW).sort((a, b) => a.score - b.score)
}

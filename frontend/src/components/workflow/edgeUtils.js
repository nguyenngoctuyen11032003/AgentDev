/**
 * Edge helpers shared by the workflow editor (WorkflowView) and the edge renderer (WorkflowEdge).
 */

/**
 * True when an edge condition always passes, whatever spelling it uses: missing, `true`/`"true"`, or the
 * canvas default `{type: 'function', config: {name: 'true'}}` (a function condition without a name also
 * defaults to `true`). Mirrors `is_always_true_condition` in backend/agentdev/validation/check_workflow.py.
 */
export function isAlwaysTrueCondition(condition) {
  if (condition === undefined || condition === null || condition === true) return true
  if (typeof condition === 'string') return condition.trim().toLowerCase() === 'true'
  if (typeof condition === 'object' && !Array.isArray(condition) && (condition.type ?? 'function') === 'function') {
    const config = condition.config
    if (config === undefined || config === null) return true
    if (typeof config === 'object') {
      const name = config.name
      return name === undefined || name === null || (typeof name === 'string' && name.trim().toLowerCase() === 'true')
    }
  }
  return false
}

/**
 * Canvas id of the YAML edge at `index` in `edges`. Several edges may join the same pair of steps
 * (e.g. one carries the draft, one starts the next step), so the n-th edge of a pair gets a suffix;
 * the first keeps the plain `from-to` id older saved layouts use.
 */
export function yamlEdgeId(edges, index) {
  const edge = edges?.[index]
  if (!edge) return ''
  let occurrence = 0
  for (let i = 0; i < index; i += 1) {
    if (edges[i]?.from === edge.from && edges[i]?.to === edge.to) occurrence += 1
  }
  const base = `${edge.from}-${edge.to}`
  return occurrence === 0 ? base : `${base}~${occurrence + 1}`
}

/** Index in `edges` of the YAML edge with canvas id `id` (see yamlEdgeId), or -1. */
export function findYamlEdgeIndex(edges, id) {
  if (!Array.isArray(edges) || !id) return -1
  for (let i = 0; i < edges.length; i += 1) {
    if (yamlEdgeId(edges, i) === id) return i
  }
  return -1
}

const APPROVAL_WORDS = /approve|duy[eệ]t|đồng ý|dong y|(^|[^a-z])ok(e|ay)?([^a-z]|$)/i
const NEGATIVE_LOOKAHEAD_START = /^\^?\(\?!/

/**
 * 'approve' / 'reject' when a keyword condition clearly reads as a human approval decision, else ''.
 * A regex naming an approval word ("ok", "duyệt", "APPROVED"...) is the approve branch; the same regex
 * wrapped in a leading negative lookahead (`^(?!...)`) is the reject branch.
 */
export function approvalBranch(condition) {
  if (!condition || typeof condition !== 'object' || condition.type !== 'keyword') return ''
  const config = condition.config || {}
  const any = Array.isArray(config.any) ? config.any.map(String) : []
  const none = Array.isArray(config.none) ? config.none.map(String) : []
  const regex = Array.isArray(config.regex) ? config.regex.map(String) : []
  if (regex.length === 1 && !any.length && !none.length && APPROVAL_WORDS.test(regex[0])) {
    return NEGATIVE_LOOKAHEAD_START.test(regex[0].trim()) ? 'reject' : 'approve'
  }
  if (any.length && !regex.length && !none.length && any.every(word => APPROVAL_WORDS.test(word))) return 'approve'
  if (none.length && !regex.length && !any.length && none.every(word => APPROVAL_WORDS.test(word))) return 'reject'
  return ''
}

export const EDGE_LABEL_MAX = 24

/** `text` cut to `max` characters with an ellipsis (whole text when it already fits). */
export function shortenLabel(text, max = EDGE_LABEL_MAX) {
  const value = String(text ?? '').replace(/\s+/g, ' ').trim()
  return value.length > max ? `${value.slice(0, max).trimEnd()}…` : value
}

export const PARALLEL_EDGE_STEP = 32

/**
 * Where edge `id` sits among the edges joining the same two steps (either direction; visual-only
 * `data.virtual` edges are ignored). `offset` is the perpendicular shift, in px, of the edge's curve in
 * its own source→target frame: 0 for the first edge of the pair, then +step, -step, +2·step... so no two
 * edges of a pair share a path. `sameDirIndex` counts only the earlier edges with the same direction
 * (used by arc-shaped edges, which are separated by radius instead).
 */
export function parallelEdgeInfo(edges, id, step = PARALLEL_EDGE_STEP) {
  const none = { index: 0, count: 1, offset: 0, sameDirIndex: 0 }
  if (!Array.isArray(edges) || !id) return none
  const self = edges.find(edge => edge?.id === id)
  if (!self || self.data?.virtual) return none
  const [low, high] = [self.source, self.target].sort()
  let index = 0
  let count = 0
  let sameDirIndex = 0
  let seenSelf = false
  for (const edge of edges) {
    if (!edge || edge.data?.virtual) continue
    const [a, b] = [edge.source, edge.target].sort()
    if (a !== low || b !== high) continue
    if (edge.id === id) {
      seenSelf = true
    } else if (!seenSelf) {
      index += 1
      if (edge.source === self.source && edge.target === self.target) sameDirIndex += 1
    }
    count += 1
  }
  const magnitude = Math.ceil(index / 2) * step
  const canonical = index % 2 === 1 ? magnitude : -magnitude
  // The perpendicular of a reversed edge points the other way, so flip to keep the pair apart
  const offset = (self.source === low ? canonical : -canonical) || 0
  return { index, count, offset, sameDirIndex }
}

function bezierControl(position, x1, y1, x2, y2, curvature) {
  const control = distance => (distance >= 0 ? 0.5 * distance : curvature * 25 * Math.sqrt(-distance))
  switch (position) {
    case 'left': return [x1 - control(x1 - x2), y1]
    case 'right': return [x1 + control(x2 - x1), y1]
    case 'top': return [x1, y1 - control(y1 - y2)]
    default: return [x1, y1 + control(y2 - y1)]
  }
}

/**
 * Cubic bezier like Vue Flow's getBezierPath, with both control points pushed `offset` px sideways
 * (perpendicular to source→target) so that parallel edges fan out. Returns [path, labelX, labelY], the
 * label sitting on the curve's own midpoint.
 */
export function offsetBezierPath({ sourceX, sourceY, sourcePosition = 'bottom', targetX, targetY, targetPosition = 'top', curvature = 0.25 }, offset = 0) {
  const [c1x, c1y] = bezierControl(sourcePosition, sourceX, sourceY, targetX, targetY, curvature)
  const [c2x, c2y] = bezierControl(targetPosition, targetX, targetY, sourceX, sourceY, curvature)
  const dx = targetX - sourceX
  const dy = targetY - sourceY
  const length = Math.hypot(dx, dy)
  const [nx, ny] = length ? [-dy / length, dx / length] : [0, -1]
  // The curve's midpoint moves by 3/4 of the control-point shift
  const shift = (offset * 4) / 3
  const s1x = c1x + nx * shift
  const s1y = c1y + ny * shift
  const s2x = c2x + nx * shift
  const s2y = c2y + ny * shift
  const labelX = sourceX * 0.125 + s1x * 0.375 + s2x * 0.375 + targetX * 0.125
  const labelY = sourceY * 0.125 + s1y * 0.375 + s2y * 0.375 + targetY * 0.125
  return [`M${sourceX},${sourceY} C${s1x},${s1y} ${s2x},${s2y} ${targetX},${targetY}`, labelX, labelY]
}

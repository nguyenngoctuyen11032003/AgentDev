/**
 * Picking a canvas spot for a newly created workflow node.
 */

export const DEFAULT_NODE_SIZE = { width: 220, height: 90 }
const GAP = 40

function boxOf(node) {
  const x = node?.position?.x
  const y = node?.position?.y
  if (typeof x !== 'number' || typeof y !== 'number') return null
  const width = node?.dimensions?.width || DEFAULT_NODE_SIZE.width
  const height = node?.dimensions?.height || DEFAULT_NODE_SIZE.height
  return { x, y, width, height }
}

function overlaps(a, b, gap) {
  return a.x < b.x + b.width + gap && b.x < a.x + a.width + gap
    && a.y < b.y + b.height + gap && b.y < a.y + a.height + gap
}

/**
 * Top-left position for a node of `size` as close as possible to `desired` without overlapping (or
 * touching within `gap` px) any node in `nodes` ({position, dimensions?}). Candidates are tried on a
 * grid of node-sized steps around `desired`, below / right of it first, nearest first.
 */
export function findFreeNodePosition(desired, nodes, { size = DEFAULT_NODE_SIZE, gap = GAP, maxRings = 30 } = {}) {
  const origin = {
    x: Number.isFinite(desired?.x) ? desired.x : 0,
    y: Number.isFinite(desired?.y) ? desired.y : 0
  }
  const boxes = (Array.isArray(nodes) ? nodes : []).map(boxOf).filter(Boolean)
  const fits = (point) => !boxes.some(box => overlaps({ ...point, ...size }, box, gap))
  if (fits(origin)) return origin

  const stepX = size.width + gap
  const stepY = size.height + gap
  for (let ring = 1; ring <= maxRings; ring += 1) {
    const candidates = []
    for (let i = -ring; i <= ring; i += 1) {
      for (let j = -ring; j <= ring; j += 1) {
        if (Math.max(Math.abs(i), Math.abs(j)) !== ring) continue
        candidates.push({ i, j })
      }
    }
    // Below / right of the desired spot first, then the other sides; nearest first within each group
    const back = ({ i, j }) => (i < 0 || j < 0 ? 1 : 0)
    const distance = ({ i, j }) => Math.hypot(i * stepX, j * stepY)
    candidates.sort((a, b) => (back(a) - back(b)) || (distance(a) - distance(b)))
    for (const { i, j } of candidates) {
      const point = { x: origin.x + i * stepX, y: origin.y + j * stepY }
      if (fits(point)) return point
    }
  }
  return { x: origin.x + stepX, y: origin.y }
}

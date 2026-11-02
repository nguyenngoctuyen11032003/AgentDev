/**
 * Grid A* pathfinding over the office map with line-of-sight smoothing,
 * so agents walk around desks and through doors instead of through walls.
 */
import { OFFICE_WIDTH, OFFICE_HEIGHT, OBSTACLES } from './officeLayout.js'

const CELL = 4
const CLEARANCE = 5 // keeps walkers from brushing against furniture edges

export class OfficePathfinder {
  constructor(obstacles = OBSTACLES) {
    this.cols = Math.ceil(OFFICE_WIDTH / CELL)
    this.rows = Math.ceil(OFFICE_HEIGHT / CELL)
    this.blocked = new Uint8Array(this.cols * this.rows)

    for (const [x, y, w, h] of obstacles) {
      const x0 = Math.max(0, Math.floor((x - CLEARANCE) / CELL))
      const y0 = Math.max(0, Math.floor((y - CLEARANCE) / CELL))
      const x1 = Math.min(this.cols - 1, Math.floor((x + w + CLEARANCE) / CELL))
      const y1 = Math.min(this.rows - 1, Math.floor((y + h + CLEARANCE) / CELL))
      for (let cy = y0; cy <= y1; cy++) {
        for (let cx = x0; cx <= x1; cx++) this.blocked[cy * this.cols + cx] = 1
      }
    }
  }

  toCell(x, y) {
    return [
      Math.min(this.cols - 1, Math.max(0, Math.floor(x / CELL))),
      Math.min(this.rows - 1, Math.max(0, Math.floor(y / CELL))),
    ]
  }

  toPoint(cx, cy) {
    return { x: cx * CELL + CELL / 2, y: cy * CELL + CELL / 2 }
  }

  isFree(cx, cy) {
    return cx >= 0 && cy >= 0 && cx < this.cols && cy < this.rows && !this.blocked[cy * this.cols + cx]
  }

  isFreePoint(x, y) {
    return this.isFree(...this.toCell(x, y))
  }

  /** Closest walkable cell to a point (seats on sofas sit inside furniture). */
  nearestFree(x, y) {
    const [sx, sy] = this.toCell(x, y)
    if (this.isFree(sx, sy)) return [sx, sy]
    for (let r = 1; r < 40; r++) {
      let best = null
      let bestDist = Infinity
      for (let dy = -r; dy <= r; dy++) {
        for (let dx = -r; dx <= r; dx++) {
          if (Math.max(Math.abs(dx), Math.abs(dy)) !== r) continue
          if (!this.isFree(sx + dx, sy + dy)) continue
          const d = dx * dx + dy * dy
          if (d < bestDist) { bestDist = d; best = [sx + dx, sy + dy] }
        }
      }
      if (best) return best
    }
    return [sx, sy]
  }

  /** Straight walk check between two cells (supercover line). */
  lineOfSight(ax, ay, bx, by) {
    let x = ax, y = ay
    const dx = Math.abs(bx - ax), dy = Math.abs(by - ay)
    const sx = ax < bx ? 1 : -1, sy = ay < by ? 1 : -1
    let err = dx - dy
    while (x !== bx || y !== by) {
      if (!this.isFree(x, y)) return false
      const e2 = 2 * err
      if (e2 > -dy) { err -= dy; x += sx }
      if (e2 < dx) { err += dx; y += sy }
      // Avoid cutting through diagonal corners.
      if (!this.isFree(x, y)) return false
    }
    return true
  }

  /**
   * Find a smoothed walking path between two map points.
   * The returned list starts after `from` and always ends exactly at `to`.
   * @returns {{x:number,y:number}[]}
   */
  findPath(from, to) {
    const [sx, sy] = this.nearestFree(from.x, from.y)
    const [gx, gy] = this.nearestFree(to.x, to.y)
    const cols = this.cols
    const start = sy * cols + sx
    const goal = gy * cols + gx

    const g = new Float32Array(cols * this.rows).fill(Infinity)
    const parent = new Int32Array(cols * this.rows).fill(-1)
    const closed = new Uint8Array(cols * this.rows)
    const heap = new MinHeap()
    const h = (i) => {
      const dx = Math.abs((i % cols) - gx), dy = Math.abs(Math.floor(i / cols) - gy)
      return Math.max(dx, dy) + (Math.SQRT2 - 1) * Math.min(dx, dy)
    }

    g[start] = 0
    heap.push(start, h(start))
    let found = start === goal

    while (heap.size && !found) {
      const cur = heap.pop()
      if (closed[cur]) continue
      closed[cur] = 1
      const cx = cur % cols, cy = Math.floor(cur / cols)
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          if (!dx && !dy) continue
          const nx = cx + dx, ny = cy + dy
          if (!this.isFree(nx, ny)) continue
          if (dx && dy && (!this.isFree(cx + dx, cy) || !this.isFree(cx, cy + dy))) continue
          const ni = ny * cols + nx
          if (closed[ni]) continue
          const cost = g[cur] + (dx && dy ? Math.SQRT2 : 1)
          if (cost < g[ni]) {
            g[ni] = cost
            parent[ni] = cur
            if (ni === goal) { found = true; break }
            heap.push(ni, cost + h(ni))
          }
        }
        if (found) break
      }
    }

    if (!found) return [{ x: to.x, y: to.y }]

    // Rebuild the cell path.
    const cells = []
    for (let i = goal; i !== -1; i = parent[i]) {
      cells.push([i % cols, Math.floor(i / cols)])
      if (i === start) break
    }
    cells.reverse()

    // String-pull: keep only the corners that are needed.
    const smooth = [cells[0]]
    let anchor = 0
    for (let i = 2; i < cells.length; i++) {
      const [ax, ay] = cells[anchor]
      const [bx, by] = cells[i]
      if (!this.lineOfSight(ax, ay, bx, by)) {
        anchor = i - 1
        smooth.push(cells[anchor])
      }
    }
    if (cells.length > 1) smooth.push(cells[cells.length - 1])

    const points = smooth.slice(1).map(([cx, cy]) => this.toPoint(cx, cy))
    // Step off the furniture first when starting inside it (e.g. from a sofa seat).
    if (!this.isFreePoint(from.x, from.y)) points.unshift(this.toPoint(sx, sy))
    points.push({ x: to.x, y: to.y })
    return dedupe(points)
  }
}

function dedupe(points) {
  const out = []
  for (const p of points) {
    const last = out[out.length - 1]
    if (!last || Math.hypot(last.x - p.x, last.y - p.y) > 0.5) out.push(p)
  }
  return out
}

class MinHeap {
  constructor() { this.items = []; this.prio = [] }
  get size() { return this.items.length }
  push(item, p) {
    const a = this.items, q = this.prio
    a.push(item); q.push(p)
    let i = a.length - 1
    while (i > 0) {
      const par = (i - 1) >> 1
      if (q[par] <= q[i]) break
      ;[a[par], a[i]] = [a[i], a[par]]
      ;[q[par], q[i]] = [q[i], q[par]]
      i = par
    }
  }
  pop() {
    const a = this.items, q = this.prio
    const top = a[0]
    const lastItem = a.pop(), lastPrio = q.pop()
    if (a.length) {
      a[0] = lastItem; q[0] = lastPrio
      let i = 0
      for (;;) {
        const l = 2 * i + 1, r = l + 1
        let m = i
        if (l < a.length && q[l] < q[m]) m = l
        if (r < a.length && q[r] < q[m]) m = r
        if (m === i) break
        ;[a[m], a[i]] = [a[i], a[m]]
        ;[q[m], q[i]] = [q[i], q[m]]
        i = m
      }
    }
    return top
  }
}

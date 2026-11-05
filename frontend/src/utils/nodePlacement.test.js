import { describe, expect, it } from 'vitest'
import { findFreeNodePosition, DEFAULT_NODE_SIZE } from './nodePlacement.js'

const node = (x, y, width = DEFAULT_NODE_SIZE.width, height = DEFAULT_NODE_SIZE.height) => ({ position: { x, y }, dimensions: { width, height } })

describe('findFreeNodePosition', () => {
  it('keeps the desired spot when it is free', () => {
    expect(findFreeNodePosition({ x: 10, y: 20 }, [node(1000, 1000)])).toEqual({ x: 10, y: 20 })
    expect(findFreeNodePosition({ x: 10, y: 20 }, [])).toEqual({ x: 10, y: 20 })
  })

  it('moves a node off an existing node to the nearest free neighbour (below)', () => {
    const pos = findFreeNodePosition({ x: 100, y: 100 }, [node(100, 100)])
    expect(pos).toEqual({ x: 100, y: 100 + DEFAULT_NODE_SIZE.height + 40 })
  })

  it('goes right when the spot below is taken', () => {
    const pos = findFreeNodePosition({ x: 100, y: 100 }, [node(100, 100), node(100, 230)])
    expect(pos).toEqual({ x: 100 + DEFAULT_NODE_SIZE.width + 40, y: 100 })
  })

  it('never returns a spot overlapping any node, even in a crowded area', () => {
    const nodes = [node(100, 100), node(360, 100), node(100, 230), node(-160, 100)]
    const pos = findFreeNodePosition({ x: 100, y: 100 }, nodes)
    for (const other of nodes) {
      const apart = pos.x >= other.position.x + other.dimensions.width || other.position.x >= pos.x + DEFAULT_NODE_SIZE.width
        || pos.y >= other.position.y + other.dimensions.height || other.position.y >= pos.y + DEFAULT_NODE_SIZE.height
      expect(apart).toBe(true)
    }
  })

  it('places successive new nodes at distinct spots', () => {
    const nodes = []
    for (let k = 0; k < 4; k += 1) {
      const pos = findFreeNodePosition({ x: 0, y: 0 }, nodes)
      expect(nodes.some(n => n.position.x === pos.x && n.position.y === pos.y)).toBe(false)
      nodes.push(node(pos.x, pos.y))
    }
  })

  it('ignores nodes without a position and falls back to the origin for a bad desired point', () => {
    expect(findFreeNodePosition(null, [{ id: 'x' }])).toEqual({ x: 0, y: 0 })
  })
})

import { describe, expect, it } from 'vitest'
import { parallelEdgeInfo, offsetBezierPath, PARALLEL_EDGE_STEP } from './edgeUtils.js'

const e = (id, source, target, data = {}) => ({ id, source, target, data })

describe('parallelEdgeInfo', () => {
  it('leaves a lone edge on its plain path', () => {
    expect(parallelEdgeInfo([e('A-B', 'A', 'B')], 'A-B')).toEqual({ index: 0, count: 1, offset: 0, sameDirIndex: 0 })
    expect(parallelEdgeInfo([], 'missing').offset).toBe(0)
  })

  it('gives each edge of the same pair a distinct offset', () => {
    const edges = [e('A-B', 'A', 'B'), e('A-B~2', 'A', 'B'), e('A-B~3', 'A', 'B'), e('X-Y', 'X', 'Y')]
    const offsets = edges.slice(0, 3).map(edge => parallelEdgeInfo(edges, edge.id).offset)
    expect(offsets).toEqual([0, PARALLEL_EDGE_STEP, -PARALLEL_EDGE_STEP])
    expect(parallelEdgeInfo(edges, 'A-B~2')).toMatchObject({ index: 1, count: 3, sameDirIndex: 1 })
    expect(parallelEdgeInfo(edges, 'X-Y').offset).toBe(0)
  })

  it('separates reversed pairs and flips the sign into the edge own frame', () => {
    const edges = [e('A-B', 'A', 'B'), e('B-A', 'B', 'A'), e('B-A~2', 'B', 'A')]
    expect(parallelEdgeInfo(edges, 'A-B').offset).toBe(0)
    // canonical +24 for index 1, expressed in the reversed edge frame
    expect(parallelEdgeInfo(edges, 'B-A').offset).toBe(-PARALLEL_EDGE_STEP)
    expect(parallelEdgeInfo(edges, 'B-A')).toMatchObject({ sameDirIndex: 0 })
    expect(parallelEdgeInfo(edges, 'B-A~2')).toMatchObject({ offset: PARALLEL_EDGE_STEP, sameDirIndex: 1 })
  })

  it('ignores visual-only team links', () => {
    const edges = [e('team:A->B', 'A', 'B', { virtual: true }), e('A-B', 'A', 'B')]
    expect(parallelEdgeInfo(edges, 'A-B').offset).toBe(0)
    expect(parallelEdgeInfo(edges, 'team:A->B').offset).toBe(0)
  })
})

describe('offsetBezierPath', () => {
  const params = { sourceX: 0, sourceY: 0, sourcePosition: 'right', targetX: 200, targetY: 0, targetPosition: 'left' }

  it('matches the plain bezier midpoint without offset', () => {
    const [path, x, y] = offsetBezierPath(params, 0)
    expect(path).toBe('M0,0 C100,0 100,0 200,0')
    expect([x, y]).toEqual([100, 0])
  })

  it('moves the curve and its label sideways by the offset', () => {
    const [pathUp, , yUp] = offsetBezierPath(params, 24)
    const [pathDown, , yDown] = offsetBezierPath(params, -24)
    expect(yUp).toBeCloseTo(24)
    expect(yDown).toBeCloseTo(-24)
    expect(pathUp).not.toBe(pathDown)
    expect(pathUp.startsWith('M0,0 ')).toBe(true)
    expect(pathUp.endsWith(' 200,0')).toBe(true)
  })
})

import { describe, expect, it } from 'vitest'
import { qualityRows, weakDimensions } from './labQuality.js'

describe('lab quality rows', () => {
  it('keeps rubric order, skips unknown or unscored dimensions and sets the tone', () => {
    const rows = qualityRows({
      craft: { score: 4, note: 'có TODO' },
      requirements: 8,
      bogus: 1,
      verification: { score: null },
      correctness: { score: 6 }
    })
    expect(rows.map((r) => [r.key, r.score, r.tone])).toEqual([
      ['requirements', 8, 'ok'],
      ['correctness', 6, 'mid'],
      ['craft', 4, 'low']
    ])
    expect(rows[2].note).toBe('có TODO')
  })

  it('returns nothing for old verdicts without dimensions', () => {
    expect(qualityRows(undefined)).toEqual([])
    expect(qualityRows({})).toEqual([])
  })

  it('lists weak dimensions lowest first', () => {
    expect(weakDimensions({ requirements: 9, craft: 6, verification: 3 }).map((r) => r.key)).toEqual(['verification', 'craft'])
  })
})

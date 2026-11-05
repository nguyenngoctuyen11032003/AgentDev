import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { LAB_TAB, labTabFromQuery, nextLabTab } from './labTabs.js'

describe('lab tabs', () => {
  it('reads the tab from the query, defaulting to score', () => {
    expect(labTabFromQuery('batch')).toBe(LAB_TAB.BATCH)
    expect(labTabFromQuery(['batch'])).toBe(LAB_TAB.BATCH)
    expect(labTabFromQuery(undefined)).toBe(LAB_TAB.SCORE)
    expect(labTabFromQuery('nonsense')).toBe(LAB_TAB.SCORE)
  })
  it('moves with arrow keys and wraps', () => {
    expect(nextLabTab('score', 'ArrowRight')).toBe('batch')
    expect(nextLabTab('batch', 'ArrowRight')).toBe('score')
    expect(nextLabTab('score', 'ArrowLeft')).toBe('batch')
    expect(nextLabTab('score', 'x')).toBeNull()
  })
  it('/batch-run is a deep link into the Lab batch tab and Lab has one entry point', () => {
    const router = readFileSync(new URL('../router/index.js', import.meta.url), 'utf8')
    expect(router).toMatch(/path: '\/batch-run'[\s\S]{0,120}redirect/)
    expect(router).toContain("tab: 'batch'")
    expect(router).toContain('LabWorkbench.vue')
    const lab = readFileSync(new URL('./LabView.vue', import.meta.url), 'utf8')
    expect(lab).not.toContain('to="/batch-run"')
  })
})

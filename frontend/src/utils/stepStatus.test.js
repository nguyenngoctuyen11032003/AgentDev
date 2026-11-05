import { describe, it, expect } from 'vitest'
import { stepStatus } from './runTracker.js'
import { STEP_STATUS } from '@/components/launch/runStatus.js'
import { stepProgress } from './runProgress.js'

const never = { runs: [] }
describe('stepStatus skipped', () => {
  it('a step that never ran is todo while the run is live, skipped once it completed', () => {
    expect(stepStatus(never, '')).toBe('todo')
    expect(stepStatus(never, 'completed')).toBe(STEP_STATUS.SKIPPED)
    expect(STEP_STATUS.SKIPPED).toBe('skipped')
  })
  it('a cancelled or failed run does not call untouched steps skipped', () => {
    expect(stepStatus(never, 'cancelled')).toBe('todo')
    expect(stepStatus(never, 'error')).toBe('todo')
  })
  it('a waiting step is never skipped', () => {
    expect(stepStatus({ runs: [], waiting: true }, 'completed')).toBe('waiting')
  })
  it('skipped steps leave the progress denominator', () => {
    expect(stepProgress(['done', 'skipped', 'done'], 'completed')).toEqual({ done: 2, total: 2, percent: 100 })
  })
})

import { modelCallStats } from './runTracker.js'
describe('modelCallStats', () => {
  it('counts only runs that called a model (literal and human steps do not)', () => {
    const runs = [{ models: 2 }, { models: 0 }, { models: 1 }]
    expect(modelCallStats(runs)).toEqual({ calls: 3, runs: 2 })
  })
})

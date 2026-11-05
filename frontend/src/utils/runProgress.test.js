import { describe, it, expect } from 'vitest'
import { stepProgress } from './runProgress.js'

describe('stepProgress', () => {
  it('counts only steps that ran once the run completed (untaken branch)', () => {
    expect(stepProgress(['done', 'done', 'todo', 'done'], 'completed')).toEqual({ done: 3, total: 3, percent: 100 })
  })
  it('keeps a skipped failed step as run', () => {
    expect(stepProgress(['done', 'done', 'done', 'done', 'done', 'error'], 'completed')).toMatchObject({ done: 5, total: 6, percent: 83 })
  })
  it('keeps all steps while the run is live', () => {
    expect(stepProgress(['done', 'working', 'todo'], '')).toEqual({ done: 1, total: 3, percent: 33 })
  })
  it('does not discount todo steps of a cancelled run', () => {
    expect(stepProgress(['done', 'todo'], 'cancelled').percent).toBe(50)
  })
  it('is 0 for no steps', () => {
    expect(stepProgress([], 'completed').percent).toBe(0)
  })
})

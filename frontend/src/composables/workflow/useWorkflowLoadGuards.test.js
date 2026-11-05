import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createSequenceGuard, createLayoutSaver, ONLY_RENDER_VISIBLE_THRESHOLD, shouldOnlyRenderVisible } from './useWorkflowLoadGuards.js'

describe('createSequenceGuard (A7-3)', () => {
  it('marks an older token stale once a newer one starts', () => {
    const guard = createSequenceGuard()
    const a = guard.next()
    expect(guard.isStale(a)).toBe(false)
    const b = guard.next()
    expect(guard.isStale(a)).toBe(true)
    expect(guard.isStale(b)).toBe(false)
  })

  it('late result of the older load is dropped', async () => {
    const guard = createSequenceGuard()
    let content = ''
    const load = async (name, delay) => {
      const seq = guard.next()
      await new Promise(r => setTimeout(r, delay))
      if (guard.isStale(seq)) return
      content = name
    }
    await Promise.all([load('first', 20), load('second', 1)])
    expect(content).toBe('second')
  })
})

describe('shouldOnlyRenderVisible (A7-1)', () => {
  it('turns on only above the threshold', () => {
    expect(ONLY_RENDER_VISIBLE_THRESHOLD).toBe(60)
    expect(shouldOnlyRenderVisible(60)).toBe(false)
    expect(shouldOnlyRenderVisible(61)).toBe(true)
  })
})

describe('createLayoutSaver (A7-2)', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('notifies once for a burst of failed saves', async () => {
    const notify = vi.fn()
    const saver = createLayoutSaver({ save: async () => false, notify, cooldownMs: 3000 })
    await saver.save()
    await saver.save()
    await saver.save()
    expect(notify).toHaveBeenCalledTimes(1)
  })

  it('notifies again after the cooldown and when save throws', async () => {
    const notify = vi.fn()
    const saver = createLayoutSaver({ save: async () => { throw new Error('x') }, notify, cooldownMs: 3000 })
    await saver.save()
    vi.advanceTimersByTime(3500)
    await saver.save()
    expect(notify).toHaveBeenCalledTimes(2)
  })

  it('does not notify on success', async () => {
    const notify = vi.fn()
    const saver = createLayoutSaver({ save: async () => true, notify })
    expect(await saver.save()).toBe(true)
    expect(notify).not.toHaveBeenCalled()
  })
})

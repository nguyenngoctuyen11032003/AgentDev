import { describe, it, expect } from 'vitest'
import { buildOptions, selectedNames, toggledValue } from './skillPickerLogic.js'
import { createLatest } from '@/utils/latestOnly.js'

const library = [
  { name: 'ok', valid: true, description: 'fine' },
  { name: 'bad', valid: false, description: '' }
]

describe('skill picker selection', () => {
  it('A5-03: "every skill" mode does not count malformed skills, and untick never stores them', () => {
    const value = { enabled: true, allow: [] }
    expect(selectedNames(value, library)).toEqual(['ok'])
    const next = toggledValue(selectedNames(value, library), 'ok', false)
    expect(next).toBeNull()
    const two = [...library, { name: 'ok2', valid: true, description: '' }]
    const after = toggledValue(selectedNames(value, two), 'ok', false)
    expect(after.allow.map((a) => a.name)).toEqual(['ok2'])
  })

  it('keeps deleted-but-ticked skills visible and flagged missing', () => {
    const opts = buildOptions({ enabled: true, allow: [{ name: 'gone' }] }, library)
    expect(opts.map((o) => o.name)).toEqual(['ok', 'gone'])
    expect(opts[1].missing).toBe(true)
  })
})

describe('createLatest', () => {
  it('A5-02: a slow older request is stale once a newer one began', async () => {
    const latest = createLatest()
    const state = { content: '' }
    const open = async (name, delay) => {
      const ticket = latest.begin()
      await new Promise((r) => setTimeout(r, delay))
      if (!latest.isCurrent(ticket)) return
      state.content = `content of ${name}`
    }
    await Promise.all([open('A', 30), open('B', 1)])
    expect(state.content).toBe('content of B')
  })

  it('cancel invalidates pending tickets', () => {
    const latest = createLatest()
    const t = latest.begin()
    latest.cancel()
    expect(latest.isCurrent(t)).toBe(false)
  })
})

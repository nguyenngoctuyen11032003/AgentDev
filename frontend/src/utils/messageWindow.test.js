import { describe, it, expect } from 'vitest'
import { WINDOW, openAtLatest, showOlder, showNewer, onLengthChange, revealIndex, sliceWindow, hiddenOlder, hiddenNewer } from './messageWindow'

const list = (n) => Array.from({ length: n }, (_, i) => i)

describe('messageWindow', () => {
  it('opens at the latest messages', () => {
    expect(openAtLatest(50)).toEqual({ start: 0, end: null })
    expect(openAtLatest(1000)).toEqual({ start: 1000 - WINDOW.limit, end: null })
  })

  it('never renders more than max items however often older is shown', () => {
    let win = openAtLatest(1000)
    for (let i = 0; i < 40; i++) {
      win = showOlder(win, 1000)
      expect(sliceWindow(list(1000), win).length).toBeLessThanOrEqual(WINDOW.max)
    }
    expect(win.start).toBe(0)
    expect(win.end).toBe(WINDOW.max)
    expect(hiddenOlder(win)).toBe(0)
    expect(hiddenNewer(win, 1000)).toBe(1000 - WINDOW.max)
  })

  it('showNewer walks back to the tail and returns to follow mode', () => {
    let win = { start: 0, end: WINDOW.max }
    for (let i = 0; i < 40; i++) win = showNewer(win, 1000)
    expect(win.end).toBeNull()
    expect(sliceWindow(list(1000), win).at(-1)).toBe(999)
    expect(sliceWindow(list(1000), win).length).toBeLessThanOrEqual(WINDOW.max)
  })

  it('slides the tail window only while at the bottom', () => {
    const win = { start: 0, end: null }
    expect(onLengthChange(win, WINDOW.limit + WINDOW.step + 5, true).start).toBe(WINDOW.step + 5)
    expect(onLengthChange(win, WINDOW.limit + WINDOW.step + 5, false).start).toBe(0)
  })

  it('does not slide a window that is pinned away from the tail', () => {
    const win = { start: 10, end: 100 }
    expect(onLengthChange(win, 2000, true)).toEqual(win)
  })

  it('clamps when the list shrinks', () => {
    expect(onLengthChange({ start: 500, end: 600 }, 20, true)).toEqual({ start: 20, end: null })
  })

  it('reveals an index that is out of the window', () => {
    const win = revealIndex(openAtLatest(1000), 1000, 100)
    expect(win.start).toBeLessThanOrEqual(100)
    expect(sliceWindow(list(1000), win).length).toBeLessThanOrEqual(WINDOW.max)
    expect(sliceWindow(list(1000), win)).toContain(100)
  })
})

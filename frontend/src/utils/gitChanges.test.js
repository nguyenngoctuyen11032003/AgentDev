import { describe, expect, it } from 'vitest'
import {
  canUndo,
  countStates,
  defaultSelection,
  diffLines,
  panelView,
  splitPath,
  summarizeUndo
} from './gitChanges.js'

const file = (path, state = 'pending') => ({ path, state, change: 'modified' })

describe('panelView', () => {
  it('maps every state', () => {
    expect(panelView({ loading: true, error: null, result: null })).toBe('loading')
    expect(panelView({ loading: false, error: new Error('x'), result: null })).toBe('error')
    expect(panelView({ loading: false, error: null, result: { status: 'running', files: [] } })).toBe('running')
    expect(panelView({ loading: false, error: null, result: { status: 'not_git', files: [] } })).toBe('unavailable')
    expect(panelView({ loading: false, error: null, result: { status: 'disabled', files: [] } })).toBe('unavailable')
    expect(panelView({ loading: false, error: null, result: { status: 'no_checkpoint', files: [] } })).toBe('unavailable')
    expect(panelView({ loading: false, error: null, result: { status: 'error', files: [] } })).toBe('error')
    expect(panelView({ loading: false, error: null, result: { status: 'ok', files: [] } })).toBe('empty')
    expect(panelView({ loading: false, error: null, result: { status: 'ok', files: [file('a')] } })).toBe('ready')
  })
  it('keeps showing the data while reloading', () => {
    expect(panelView({ loading: true, error: null, result: { status: 'ok', files: [file('a')] } })).toBe('ready')
  })
})

describe('states and undo', () => {
  it('counts and gates undo on pending files', () => {
    const files = [file('a'), file('b', 'conflict'), file('c', 'reverted')]
    expect(countStates(files)).toEqual({ pending: 1, reverted: 1, conflict: 1 })
    expect(canUndo(files)).toBe(true)
    expect(canUndo([file('b', 'conflict'), file('c', 'reverted')])).toBe(false)
    expect(canUndo(null)).toBe(false)
  })
  it('summarizes an undo response', () => {
    expect(summarizeUndo({ restored: ['a'], removed: ['b'], conflicts: [], errors: [] })).toMatchObject({ tone: 'success', done: 2 })
    expect(summarizeUndo({ restored: ['a'], conflicts: [{ path: 'x' }] })).toMatchObject({ tone: 'warn', done: 1 })
    expect(summarizeUndo({ conflicts: [{ path: 'x' }] })).toMatchObject({ tone: 'error', done: 0 })
    expect(summarizeUndo(null).tone).toBe('success')
  })
  it('selects a pending file first', () => {
    expect(defaultSelection([file('a', 'reverted'), file('b')])).toBe('b')
    expect(defaultSelection([file('a', 'conflict')])).toBe('a')
    expect(defaultSelection([])).toBe('')
  })
})

describe('diff and path helpers', () => {
  it('types diff lines', () => {
    expect(diffLines('@@ -1 +1 @@\n-old\n+new\n same\r\n').map((l) => l.type)).toEqual(['hunk', 'del', 'add', 'ctx', 'ctx'])
    expect(diffLines('')).toEqual([])
  })
  it('splits paths', () => {
    expect(splitPath('src/app/a.js')).toEqual({ dir: 'src/app/', name: 'a.js' })
    expect(splitPath('a.js')).toEqual({ dir: '', name: 'a.js' })
  })
})

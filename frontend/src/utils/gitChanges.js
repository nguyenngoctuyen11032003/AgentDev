// Pure logic of the "Thay đổi" (git checkpoint) panel of the Run page: no DOM, no i18n, no network.

export const CHANGE_STATUS = Object.freeze({
  OK: 'ok',
  RUNNING: 'running',
  NOT_GIT: 'not_git',
  DISABLED: 'disabled',
  NO_CHECKPOINT: 'no_checkpoint',
  ERROR: 'error'
})

export const FILE_STATE = Object.freeze({ PENDING: 'pending', REVERTED: 'reverted', CONFLICT: 'conflict' })

export const PANEL_VIEW = Object.freeze({
  LOADING: 'loading',
  ERROR: 'error',
  RUNNING: 'running',
  UNAVAILABLE: 'unavailable', // not a git repo / flag off / no snapshot taken: nothing to undo, say why
  EMPTY: 'empty', // a snapshot exists and the run changed no file
  READY: 'ready'
})

/** Which of the panel's screens to show. `error` wins over data, `loading` only while there is nothing yet. */
export function panelView({ loading, error, result }) {
  if (error) return PANEL_VIEW.ERROR
  if (!result) return loading ? PANEL_VIEW.LOADING : PANEL_VIEW.UNAVAILABLE
  switch (result.status) {
    case CHANGE_STATUS.OK:
      return (result.files || []).length ? PANEL_VIEW.READY : PANEL_VIEW.EMPTY
    case CHANGE_STATUS.RUNNING:
      return PANEL_VIEW.RUNNING
    case CHANGE_STATUS.ERROR:
      return PANEL_VIEW.ERROR
    default:
      return PANEL_VIEW.UNAVAILABLE
  }
}

export function countStates(files) {
  const counts = { pending: 0, reverted: 0, conflict: 0 }
  for (const file of files || []) if (file.state in counts) counts[file.state] += 1
  return counts
}

/** Undo is offered only when at least one file still holds what the run left. */
export const canUndo = (files) => countStates(files).pending > 0

/** Split a unified diff into typed lines for colouring (never inserted as HTML). */
export function diffLines(diff) {
  if (!diff) return []
  return String(diff)
    .replace(/\r$/gm, '')
    .split('\n')
    .map((text) => {
      let type = 'ctx'
      if (text.startsWith('@@')) type = 'hunk'
      else if (text.startsWith('+')) type = 'add'
      else if (text.startsWith('-')) type = 'del'
      return { type, text }
    })
}

/** Folder / file name split for a compact row: {dir: 'src/', name: 'a.js'}. */
export function splitPath(path) {
  const clean = String(path || '')
  const at = clean.lastIndexOf('/')
  return at < 0 ? { dir: '', name: clean } : { dir: clean.slice(0, at + 1), name: clean.slice(at + 1) }
}

/** Reduce an undo response to what the live region says: counts plus the per-file problems. */
export function summarizeUndo(result) {
  const restored = result?.restored || []
  const removed = result?.removed || []
  const conflicts = result?.conflicts || []
  const errors = result?.errors || []
  const done = restored.length + removed.length
  let tone = 'success'
  if (conflicts.length || errors.length) tone = done ? 'warn' : 'error'
  return { tone, restored: restored.length, removed: removed.length, conflicts, errors, done }
}

/** The file to show first: a pending one, else the first. */
export function defaultSelection(files) {
  const list = files || []
  return (list.find((f) => f.state === FILE_STATE.PENDING) || list[0] || {}).path || ''
}

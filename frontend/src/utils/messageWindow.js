// Render window for the run chat: a long session mounts at most WINDOW.max messages.
// `end: null` follows the live tail; a number means the reader walked back in history and the
// newest messages were unmounted (they come back with "show newer" or "jump to latest").
export const WINDOW = { limit: 120, step: 60, max: 180 }

const norm = (start, end, length) => (end === null || end >= length ? { start, end: null } : { start, end })

export const openAtLatest = (length) => ({ start: Math.max(0, length - WINDOW.limit), end: null })

// The user sent a message: a detached window (reader far up in history) snaps back to the tail so
// the new message and the reply are mounted.
export const followTail = (win, length) => (win.end === null ? win : openAtLatest(length))

export const sliceWindow = (list, win) => list.slice(Math.min(win.start, list.length), win.end ?? list.length)

export const hiddenOlder = (win) => win.start
export const hiddenNewer = (win, length) => (win.end === null ? 0 : Math.max(0, length - win.end))

export function showOlder(win, length) {
  const start = Math.max(0, win.start - WINDOW.step)
  let end = win.end ?? length
  if (end - start > WINDOW.max) end = start + WINDOW.max
  return norm(start, end, length)
}

export function showNewer(win, length) {
  if (win.end === null) return win
  const end = Math.min(length, win.end + WINDOW.step)
  return norm(Math.max(win.start, end - WINDOW.max), end, length)
}

export function onLengthChange(win, length, nearBottom) {
  let { start, end } = win
  if (end !== null && end >= length) end = null
  if (start > length) start = length
  if (end === null && nearBottom && length - start > WINDOW.limit + WINDOW.step) start = length - WINDOW.limit
  return { start, end }
}

export function revealIndex(win, length, index) {
  if (index < 0 || index >= length) return win
  if (index >= win.start && (win.end === null || index < win.end)) return win
  if (index < win.start) return showOlderTo(win, length, index)
  const end = Math.min(length, index + 1 + WINDOW.step)
  return norm(Math.max(0, end - WINDOW.max), end, length)
}

function showOlderTo(win, length, index) {
  const start = Math.max(0, index - WINDOW.step)
  let end = win.end ?? length
  if (end - start > WINDOW.max) end = start + WINDOW.max
  return norm(start, end, length)
}

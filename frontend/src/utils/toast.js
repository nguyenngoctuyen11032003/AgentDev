// In-app notifications (replaces window.alert so messages match the UI theme).
// Rendered by components/common/ToastHost.vue, mounted once in App.vue.
import { reactive } from 'vue'

const DEFAULT_DURATION = { success: 4000, info: 5000, warning: 8000, error: 0 }
const MAX_VISIBLE = 4

export const toasts = reactive([])
let nextId = 1

export function dismissToast(id) {
  const index = toasts.findIndex((toast) => toast.id === id)
  if (index === -1) return
  clearTimeout(toasts[index].timer)
  toasts.splice(index, 1)
}

/**
 * @param {'success'|'info'|'warning'|'error'} type
 * @param {string} title
 * @param {{detail?: string, items?: string[], duration?: number, action?: {label: string, run: () => void}}} [options]
 *   duration 0 keeps the toast until the user closes it (default for errors).
 *   action adds one button (e.g. "Open session"); clicking it also closes the toast.
 */
function show(type, title, { detail = '', items = [], duration, action = null } = {}) {
  // Same message again: refresh it instead of stacking duplicates.
  const existing = toasts.find((toast) => toast.type === type && toast.title === title && toast.detail === detail)
  if (existing) dismissToast(existing.id)

  const id = nextId++
  const ms = duration ?? DEFAULT_DURATION[type]
  toasts.push({
    id,
    type,
    title,
    detail,
    items,
    action,
    timer: ms > 0 ? setTimeout(() => dismissToast(id), ms) : null
  })
  while (toasts.length > MAX_VISIBLE) dismissToast(toasts[0].id)
  return id
}

export function runToastAction(id) {
  const item = toasts.find((toast) => toast.id === id)
  const run = item?.action?.run
  dismissToast(id)
  run?.()
}

export const toast = {
  success: (title, options) => show('success', title, options),
  info: (title, options) => show('info', title, options),
  warning: (title, options) => show('warning', title, options),
  error: (title, options) => show('error', title, options)
}

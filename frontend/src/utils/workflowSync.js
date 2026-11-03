/**
 * Cross-tab workflow change notifications.
 *
 * The editor (WorkflowWorkbench) and the run pages (Launch / Batch) usually live in
 * different browser tabs. Whenever a workflow YAML or its saved graph is written, the
 * API client calls `notifyWorkflowChanged`, and every open page that shows that
 * workflow refreshes its data (mascots, nodes, edges) right away instead of waiting
 * for a manual reload.
 *
 * Uses BroadcastChannel when available and falls back to the `storage` event.
 * Listeners in the same tab are notified too (BroadcastChannel skips the sender).
 */

const CHANNEL_NAME = 'agentdev:workflows'
const STORAGE_KEY = 'agentdev:workflow-changed'

const listeners = new Set()
let channel = null
let storageBound = false

/** Canonical workflow key: trimmed, without a `.yaml` / `.yml` suffix. */
export function workflowKey(name) {
  if (!name || typeof name !== 'string') return ''
  return name.trim().replace(/\.ya?ml$/i, '')
}

function dispatch(detail) {
  if (!detail || typeof detail !== 'object') return
  for (const listener of [...listeners]) {
    try {
      listener(detail)
    } catch (error) {
      console.error('workflow change listener failed:', error)
    }
  }
}

function ensureTransport() {
  if (typeof window === 'undefined') return
  if (!channel && typeof BroadcastChannel === 'function') {
    try {
      channel = new BroadcastChannel(CHANNEL_NAME)
      channel.onmessage = (event) => dispatch(event.data)
    } catch {
      channel = null
    }
  }
  if (!channel && !storageBound) {
    storageBound = true
    window.addEventListener('storage', (event) => {
      if (event.key !== STORAGE_KEY || !event.newValue) return
      try {
        dispatch(JSON.parse(event.newValue))
      } catch {
        // ignore malformed payloads
      }
    })
  }
}

/**
 * Announce that a workflow changed.
 * @param {string} name - Workflow file name (with or without `.yaml`).
 * @param {Object} [extra]
 * @param {'yaml'|'graph'|'rename'|'copy'} [extra.kind='yaml']
 * @param {string} [extra.previous] - Old name on rename.
 */
export function notifyWorkflowChanged(name, { kind = 'yaml', previous = '' } = {}) {
  const key = workflowKey(name)
  if (!key) return
  const detail = { key, kind, previous: workflowKey(previous), at: Date.now() }
  ensureTransport()
  dispatch(detail)
  if (channel) {
    try {
      channel.postMessage(detail)
    } catch {
      // channel closed; nothing else to do
    }
  } else {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(detail))
    } catch {
      // storage unavailable (private mode): other tabs refresh on focus instead
    }
  }
}

/**
 * Listen for workflow changes from this tab or any other tab.
 * @param {(detail: {key: string, kind: string, previous: string, at: number}) => void} listener
 * @returns {() => void} Unsubscribe function.
 */
export function onWorkflowChanged(listener) {
  ensureTransport()
  listeners.add(listener)
  return () => listeners.delete(listener)
}

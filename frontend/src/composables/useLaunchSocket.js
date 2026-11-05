// WebSocket plumbing of the Launch view: socket URL, frame parsing, the ordered incoming
// queue (one reactive pass per frame) and the reconnect backoff. What each event *does*
// stays in the view (processMessage and the `connection` handshake).

// One id per page load plus a counter per socket: the server tells our own overlapping
// sockets (reconnect, draft -> session switch) from a really different tab.
export const createClientId = () =>
  (typeof crypto !== 'undefined' && crypto.randomUUID?.()) || `c${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`

/**
 * The /ws URL: same-origin by default (works with the Vite dev proxy); in production an
 * explicit API base wins. A reconnect names the session and asks for a batched replay.
 */
export const buildSocketUrl = ({
  sessionId = '',
  clientId,
  seq,
  location = window.location,
  apiBase = import.meta.env.VITE_API_BASE_URL || '',
  dev = import.meta.env.DEV
}) => {
  // Defaults: same-origin (works with Vite dev proxy)
  let scheme = location.protocol === 'https:' ? 'wss:' : 'ws:'
  let host = location.host

  // In production, prefer explicit API base if provided
  if (!dev && apiBase) {
    try {
      const api = new URL(apiBase, location.origin)
      scheme = api.protocol === 'https:' ? 'wss:' : 'ws:'
      host = api.host
    } catch {
      // keep defaults
    }
  }

  const clientParams = `client=${encodeURIComponent(clientId)}&seq=${seq}`
  return sessionId
    ? `${scheme}//${host}/ws?session_id=${encodeURIComponent(sessionId)}&batch=1&${clientParams}`
    : `${scheme}//${host}/ws?${clientParams}`
}

/**
 * One socket frame -> what to do with it.
 * - { kind: 'batch', messages } a replay sent as one frame (object items only, in order)
 * - { kind: 'replaced' } another tab took this session
 * - { kind: 'message', msg } a single event object
 * - { kind: 'invalid', error? } malformed JSON or not an object
 */
export const parseSocketFrame = (data) => {
  let msg
  try {
    msg = JSON.parse(data)
  } catch (error) {
    return { kind: 'invalid', error }
  }
  if (msg?.type === 'batch' && Array.isArray(msg.data)) {
    return { kind: 'batch', messages: msg.data.filter((inner) => inner && typeof inner === 'object') }
  }
  if (msg?.type === 'session_replaced') return { kind: 'replaced' }
  if (!msg || typeof msg !== 'object') return { kind: 'invalid' }
  return { kind: 'message', msg }
}

/**
 * Incoming events are collected and applied together once per frame: one reactive pass
 * (and one render) for a burst instead of one per event. The order is kept, and messages
 * are handled strictly one batch after another.
 *
 * @param {object} deps
 * @param {(socket: WebSocket) => boolean} deps.isCurrent false for a socket that was replaced
 * @param {(msg: object) => Promise<unknown>} deps.process handles one event
 * @param {() => void} [deps.onFlush] a non-empty batch is about to be applied
 */
export const createIncomingQueue = ({ isCurrent, process, onFlush = () => {} }) => {
  let processQueue = Promise.resolve()
  let incomingBuffer = []
  let flushTimer = null
  let flushRaf = null
  const flushIncoming = () => {
    if (flushTimer) clearTimeout(flushTimer)
    if (flushRaf) cancelAnimationFrame(flushRaf)
    flushTimer = flushRaf = null
    const batch = incomingBuffer
    incomingBuffer = []
    if (!batch.length) return
    onFlush()
    processQueue = processQueue
      .then(async () => {
        // process runs synchronously up to its first await, so the whole batch lands in
        // one go; only session_resumed (it waits for the workflow file) is waited for.
        for (const { socket, msg } of batch) {
          if (!isCurrent(socket)) continue
          try {
            const pending = process(msg)
            if (msg.type === 'session_resumed') await pending
            else pending.catch((e) => console.error('Failed to handle a WebSocket message:', e))
          } catch (e) {
            console.error('Failed to handle a WebSocket message:', e)
          }
        }
      })
      .catch((processError) => console.error('Failed to handle a WebSocket message:', processError))
    return processQueue
  }
  const enqueue = (socket, msg) => {
    incomingBuffer.push({ socket, msg })
    if (flushTimer) return
    // rAF does not run in a hidden tab: the timer keeps the chat moving there
    flushTimer = setTimeout(flushIncoming, 50)
    if (typeof requestAnimationFrame === 'function') flushRaf = requestAnimationFrame(flushIncoming)
  }
  return { enqueue, flush: flushIncoming }
}

// 1s, 2s, 4s, 8s, then every 10s
export const reconnectDelay = (attempts) => Math.min(1000 * 2 ** attempts, 10000)

/**
 * Reconnect backoff state. `attempts` counts retries since the last good connection;
 * `auto` is set while an automatic reconnect is in flight.
 */
export const createReconnector = () => {
  let timer = null
  const state = {
    attempts: 0,
    auto: false,
    cancel() {
      clearTimeout(timer)
      timer = null
      state.attempts = 0
      state.auto = false
    },
    schedule(run) {
      clearTimeout(timer)
      const delay = reconnectDelay(state.attempts)
      state.attempts += 1
      timer = setTimeout(() => {
        timer = null
        run()
      }, delay)
    }
  }
  return state
}

import { describe, it, expect, vi, afterEach } from 'vitest'
import { buildSocketUrl, parseSocketFrame, createIncomingQueue, createReconnector, reconnectDelay } from './useLaunchSocket.js'

const location = { protocol: 'http:', host: 'localhost:5281', origin: 'http://localhost:5281' }

describe('buildSocketUrl', () => {
  it('connects same-origin for a new session', () => {
    expect(buildSocketUrl({ clientId: 'c 1', seq: 2, location, apiBase: '', dev: true })).toBe('ws://localhost:5281/ws?client=c%201&seq=2')
  })

  it('names the session and asks for a batched replay on reconnect', () => {
    expect(buildSocketUrl({ sessionId: 's/1', clientId: 'c', seq: 1, location, apiBase: '', dev: true }))
      .toBe('ws://localhost:5281/ws?session_id=s%2F1&batch=1&client=c&seq=1')
  })

  it('uses the API base in production only', () => {
    const apiBase = 'https://api.example.com/x'
    expect(buildSocketUrl({ clientId: 'c', seq: 1, location, apiBase, dev: false })).toBe('wss://api.example.com/ws?client=c&seq=1')
    expect(buildSocketUrl({ clientId: 'c', seq: 1, location, apiBase, dev: true })).toBe('ws://localhost:5281/ws?client=c&seq=1')
    expect(buildSocketUrl({ clientId: 'c', seq: 1, location: { ...location, protocol: 'https:' }, apiBase: '', dev: false })).toBe('wss://localhost:5281/ws?client=c&seq=1')
  })
})

describe('parseSocketFrame', () => {
  it('reads a single event', () => {
    expect(parseSocketFrame('{"type":"log","data":{}}')).toEqual({ kind: 'message', msg: { type: 'log', data: {} } })
  })

  it('unpacks a replay batch, keeping only objects, in order', () => {
    const frame = JSON.stringify({ type: 'batch', data: [{ type: 'a' }, null, 3, { type: 'b' }] })
    expect(parseSocketFrame(frame)).toEqual({ kind: 'batch', messages: [{ type: 'a' }, { type: 'b' }] })
  })

  it('notices the session was taken by another tab', () => {
    expect(parseSocketFrame('{"type":"session_replaced"}')).toEqual({ kind: 'replaced' })
  })

  it('rejects malformed frames and non-objects', () => {
    expect(parseSocketFrame('{oops').kind).toBe('invalid')
    expect(parseSocketFrame('{oops').error).toBeInstanceOf(SyntaxError)
    expect(parseSocketFrame('null')).toEqual({ kind: 'invalid' })
    expect(parseSocketFrame('"text"')).toEqual({ kind: 'invalid' })
  })
})

describe('createIncomingQueue', () => {
  afterEach(() => vi.useRealTimers())

  it('applies a burst in order, once, and skips stale sockets', async () => {
    vi.useFakeTimers()
    const seen = []
    const live = {}
    const stale = {}
    let flushes = 0
    const queue = createIncomingQueue({
      isCurrent: (socket) => socket === live,
      process: async (msg) => { seen.push(msg.type) },
      onFlush: () => { flushes += 1 }
    })
    queue.enqueue(live, { type: 'a' })
    queue.enqueue(stale, { type: 'x' })
    queue.enqueue(live, { type: 'b' })
    expect(seen).toEqual([])
    vi.advanceTimersByTime(50)
    await vi.runAllTimersAsync()
    expect(seen).toEqual(['a', 'b'])
    expect(flushes).toBe(1)
  })

  it('waits for session_resumed before the events after it', async () => {
    const order = []
    let release
    const socket = {}
    const queue = createIncomingQueue({
      isCurrent: () => true,
      process: (msg) => {
        order.push(`start:${msg.type}`)
        if (msg.type === 'session_resumed') return new Promise((resolve) => { release = () => { order.push('resumed'); resolve() } })
        return Promise.resolve()
      }
    })
    queue.enqueue(socket, { type: 'session_resumed' })
    const first = queue.flush()
    queue.enqueue(socket, { type: 'log' })
    const second = queue.flush()
    await Promise.resolve()
    expect(order).toEqual(['start:session_resumed'])
    release()
    await first
    await second
    expect(order).toEqual(['start:session_resumed', 'resumed', 'start:log'])
  })

  it('keeps going when one event fails', async () => {
    const seen = []
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    const queue = createIncomingQueue({
      isCurrent: () => true,
      process: (msg) => {
        if (msg.type === 'bad') throw new Error('boom')
        seen.push(msg.type)
        return Promise.resolve()
      }
    })
    queue.enqueue({}, { type: 'bad' })
    queue.enqueue({}, { type: 'ok' })
    await queue.flush()
    expect(seen).toEqual(['ok'])
    expect(errors).toHaveBeenCalled()
    errors.mockRestore()
  })
})

describe('reconnect backoff', () => {
  afterEach(() => vi.useRealTimers())

  it('doubles up to 10 seconds', () => {
    expect([0, 1, 2, 3, 4, 5].map(reconnectDelay)).toEqual([1000, 2000, 4000, 8000, 10000, 10000])
  })

  it('counts attempts and resets on cancel', () => {
    vi.useFakeTimers()
    const reconnector = createReconnector()
    let runs = 0
    reconnector.schedule(() => { runs += 1 })
    expect(reconnector.attempts).toBe(1)
    vi.advanceTimersByTime(999)
    expect(runs).toBe(0)
    vi.advanceTimersByTime(1)
    expect(runs).toBe(1)
    reconnector.schedule(() => { runs += 1 })
    expect(reconnector.attempts).toBe(2)
    reconnector.auto = true
    reconnector.cancel()
    vi.advanceTimersByTime(5000)
    expect(runs).toBe(1)
    expect(reconnector.attempts).toBe(0)
    expect(reconnector.auto).toBe(false)
  })
})

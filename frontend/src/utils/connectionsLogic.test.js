import { describe, it, expect, vi, afterEach } from 'vitest'
import { readyCount, needsLiveModels, logoutToast } from './connectionsLogic.js'
import { createGoogleOAuthFlow } from './googleOAuth.js'
import { deleteConnection } from '@/api/client.js'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('A3-02 live models', () => {
  it('skips the model listing for CLI connections (API field is authType)', () => {
    expect(needsLiveModels({ id: 'a', authType: 'cli' })).toBe(false)
    expect(needsLiveModels({ id: 'b', authType: 'oauth' })).toBe(true)
  })
})

describe('A3-05 ready count', () => {
  const conns = [
    { id: 'a', vendor: 'anthropic' },
    { id: 'b', vendor: 'openai' }
  ]
  it('does not count signed-out accounts as ready', () => {
    expect(readyCount(conns, { a: { loggedIn: true }, b: { loggedIn: false } }, 'openai')).toBe(0)
    expect(readyCount(conns, { a: { loggedIn: true } }, 'anthropic')).toBe(1)
    expect(readyCount(conns, {}, 'openai')).toBe(1)
  })
})

describe('A4-2 logout toast', () => {
  it('honors cliLoggedOut', () => {
    expect(logoutToast({ cliLoggedOut: true }, true)).toBe('logged_out_cli')
    expect(logoutToast({ cliLoggedOut: false }, true)).toBe('logout_cli_failed')
    expect(logoutToast({ cliLoggedOut: false }, false)).toBe('logged_out')
    expect(logoutToast({}, false)).toBe('logged_out')
  })
})

describe('deleteConnection sign_out_cli', () => {
  const stub = () => {
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ({}) }))
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }
  it('sends no flag by default', async () => {
    const f = stub()
    await deleteConnection('c1')
    expect(f.mock.calls[0][0]).not.toContain('sign_out_cli')
  })
  it('sends ?sign_out_cli=true when opted in', async () => {
    const f = stub()
    await deleteConnection('c1', { signOutCli: true })
    expect(f.mock.calls[0][0]).toContain('?sign_out_cli=true')
  })
})

describe('A3-04 google oauth flow', () => {
  const deps = (over = {}) => ({
    start: vi.fn(async () => ({ authUrl: 'http://x/auth', state: 's1' })),
    poll: vi.fn(async () => ({ status: 'pending' })),
    openWindow: vi.fn(() => ({ closed: false })),
    t: (k) => k,
    ...over
  })

  it('rejects when the popup is blocked', async () => {
    const flow = createGoogleOAuthFlow('lbl', deps({ openWindow: vi.fn(() => null) }))
    await expect(flow.promise).rejects.toThrow('connections.popup_blocked')
  })

  it('can be cancelled while waiting', async () => {
    vi.useFakeTimers()
    const flow = createGoogleOAuthFlow('lbl', deps())
    const caught = flow.promise.catch((e) => e)
    await vi.advanceTimersByTimeAsync(10)
    flow.cancel()
    expect((await caught).message).toBe('connections.sign_in_cancelled')
  })

  it('times out', async () => {
    vi.useFakeTimers()
    const flow = createGoogleOAuthFlow('lbl', deps({ timeoutMs: 5000 }))
    const caught = flow.promise.catch((e) => e)
    await vi.advanceTimersByTimeAsync(6000)
    expect((await caught).message).toBe('connections.sign_in_timeout')
  })

  it('resolves when polling reports done', async () => {
    vi.useFakeTimers()
    const flow = createGoogleOAuthFlow('lbl', deps({ poll: vi.fn(async () => ({ status: 'done' })) }))
    await vi.advanceTimersByTimeAsync(2000)
    await expect(flow.promise).resolves.toBe(true)
  })
})

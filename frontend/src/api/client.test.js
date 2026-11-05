import { describe, it, expect, vi, afterEach } from 'vitest'
import { openLocalProjectFile } from './client.js'

const respond = (status, body) =>
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: false, status, statusText: 'X', json: async () => body
  })))

afterEach(() => vi.unstubAllGlobals())

describe('openLocalProjectFile errors', () => {
  it('turns a pydantic 422 list into readable text', async () => {
    respond(422, { detail: [{ loc: ['body', 'relative_path'], msg: 'Field required', type: 'missing' }] })
    const err = await openLocalProjectFile('s1', '').catch((e) => e)
    expect(err.message).toContain('relative_path: Field required')
    expect(err.message).not.toContain('[object Object]')
    expect(err.status).toBe(422)
  })

  it('falls back to the HTTP status when the body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, statusText: 'Not Found', json: async () => { throw new Error('x') } })))
    const err = await openLocalProjectFile('s1', 'a').catch((e) => e)
    expect(err.message).toContain('404')
  })
})

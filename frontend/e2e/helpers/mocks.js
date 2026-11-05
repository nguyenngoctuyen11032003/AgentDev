// page.route mocks for the endpoints that would touch the user's real accounts or library.
const json = (route, body, status = 200) => route.fulfill({ status, json: body })

export const VENDORS = [
  { id: 'anthropic', label: 'Anthropic Claude', models: ['claude-sonnet-5-5', 'claude-haiku-5-5'], authMethods: ['cli'], cliProvider: 'claude_cli', cliTools: true },
  { id: 'openai', label: 'OpenAI', models: ['gpt-6.1-sol'], authMethods: ['cli'], cliProvider: 'codex_cli', cliTools: true },
  { id: 'gemini', label: 'Google Gemini', models: ['gemini-3-flash-preview'], authMethods: ['oauth'], cliProvider: null, cliTools: false },
]

export const FAKE_CONNECTION = {
  id: 'e2e-claude', vendor: 'anthropic', label: 'Claude E2E', authType: 'cli', auth_type: 'cli',
  secretHint: '', needsSignIn: false, baseUrl: '', createdAt: '2026-01-01T00:00:00+00:00',
}

/** Stateful mock of /api/connections. `state.list` can be mutated; `state.failList` makes the list answer 500. */
export async function mockConnections(page, { list = [FAKE_CONNECTION], failList = false } = {}) {
  const state = { list: [...list], failList, deleted: [], defaultId: list[0]?.id || null }
  await page.route('**/api/connections**', (route) => {
    const url = new URL(route.request().url())
    const method = route.request().method()
    const parts = url.pathname.replace(/^\/api\/connections\/?/, '').split('/').filter(Boolean)
    if (parts[0] === 'vendors') return json(route, { vendors: VENDORS })
    if (!parts.length && method === 'GET') {
      if (state.failList) return json(route, { detail: 'boom' }, 500)
      return json(route, { connections: state.list, defaultConnection: state.defaultId })
    }
    if (parts[1] === 'account') {
      return json(route, { loggedIn: true, authMethod: 'Account', displayName: 'E2E User', email: 'e2e@example.test', plan: 'Max', models: [{ id: 'claude-sonnet-5-5', name: 'Sonnet', primary: true }] })
    }
    if (parts[1] === 'test') return json(route, { ok: true, models: ['claude-sonnet-5-5'] })
    if (method === 'DELETE' && parts.length === 1) {
      state.deleted.push(parts[0])
      state.list = state.list.filter((c) => c.id !== parts[0])
      return json(route, { ok: true })
    }
    return json(route, {})
  })
  return state
}

const frontmatter = (s) => `---\nname: ${s.name}\ndescription: ${s.description}\n---\n${s.body || ''}`

/** In-memory mock of /api/skills (list, get, create, update, delete). Nothing reaches workspace/skills. */
export async function mockSkills(page, seed = []) {
  const state = { skills: seed.map((s) => ({ valid: true, extra_files: 0, ...s })), calls: [] }
  await page.route('**/api/skills**', async (route) => {
    const req = route.request()
    const method = req.method()
    const path = new URL(req.url()).pathname.replace(/^\/api\/skills\/?/, '')
    const name = decodeURIComponent(path)
    state.calls.push(`${method} /${path}`)
    const find = (n) => state.skills.find((s) => s.name === n)
    if (method === 'GET' && !path) return json(route, { skills: state.skills.map((s) => { const c = { ...s }; delete c.body; return c }) })
    if (path === 'import-source') return json(route, { source: '', exists: false, skills: [] })
    if (method === 'GET') {
      const s = find(name)
      return s ? json(route, { ...s, content: frontmatter(s) }) : json(route, { detail: 'not found' }, 404)
    }
    const data = req.postDataJSON() || {}
    const parse = (content) => {
      const m = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/.exec(content || '')
      const get = (k) => (m ? new RegExp(`^${k}:\\s*(.*)$`, 'm').exec(m[1])?.[1].trim() : '') || ''
      return { name: data.name || get('name'), description: data.description || get('description'), body: m ? m[2] : content }
    }
    if (method === 'POST') {
      const s = parse(data.content)
      if (find(s.name) && !data.overwrite) return json(route, { detail: 'exists' }, 409)
      state.skills = state.skills.filter((x) => x.name !== s.name).concat({ valid: true, extra_files: 0, ...s })
      return json(route, { name: s.name })
    }
    if (method === 'PUT') {
      const s = parse(data.content)
      state.skills = state.skills.map((x) => (x.name === name ? { valid: true, extra_files: 0, ...s } : x))
      return json(route, { name: s.name })
    }
    if (method === 'DELETE') {
      state.skills = state.skills.filter((x) => x.name !== name)
      return json(route, { ok: true })
    }
    return json(route, {})
  })
  return state
}

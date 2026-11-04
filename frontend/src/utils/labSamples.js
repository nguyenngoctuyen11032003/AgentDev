// Pure helpers for the Lab "sample scenarios" menu (no Vue / DOM, node-testable).

export const MAX_SCENARIOS = 20
export const PACK_IDS = ['general', 'dev', 'data', 'marketing', 'video', 'content', 'support', 'research']
const SCENARIOS_PER_PACK = 4

// A "word" boundary that also treats "_" and digits as separators (workflow names use snake_case).
const B0 = '(?<![a-z])'
const B1 = '(?![a-z])'
const word = (w) => `${B0}${w}${B1}`

// Order matters: first matching pack wins. "general" is the fallback.
const PACK_KEYWORDS = [
  ['video', new RegExp(['video', 'film', 'phim', 'movie', 'storyboard', 'screenwriter', 'biên kịch', 'đạo diễn', 'director', 'cinemat'].join('|'))],
  ['data', new RegExp([word('data'), 'dữ liệu', 'analyt', 'phân tích', word('bi'), word('sql')].join('|'))],
  ['marketing', new RegExp(['marketing', word('seo'), 'quảng cáo', 'social', 'growth', 'campaign'].join('|'))],
  ['support', new RegExp(['support', 'cskh', 'chăm sóc', 'customer', 'helpdesk', 'hỗ trợ'].join('|'))],
  ['research', new RegExp(['research', 'nghiên cứu', word('paper')].join('|'))],
  ['content', new RegExp(['content', 'viết', 'writer', 'biên tập', 'copywrit', 'editor', 'blog', 'article'].join('|'))],
  ['dev', new RegExp([word('dev'), word('qa'), word('code'), 'coder', 'developer', 'engineer', 'lập trình', 'software', 'phần mềm', 'tester', 'programmer', 'backend', 'frontend'].join('|'))]
]

export function detectPack(workflowName, members = []) {
  // The workflow name is the strongest signal, then the team members listed in the check report.
  const nameText = String(workflowName || '').toLowerCase()
  const allText = [nameText, ...(members || []).map((m) => String(m).toLowerCase())].join(' ')
  for (const source of [nameText, allText]) {
    for (const [id, re] of PACK_KEYWORDS) {
      if (re.test(source)) return id
    }
  }
  return 'general'
}

export function normalizePrompt(prompt) {
  return String(prompt || '').trim().replace(/\s+/g, ' ').toLowerCase()
}

// Returns { toAdd, replaceBlank }: candidates not already present (same prompt), capped so the
// final list never exceeds `max`. A single blank scenario counts as free space (it gets replaced).
export function dedupeSamples(existing, candidates, max = MAX_SCENARIOS) {
  const list = existing || []
  const replaceBlank = list.length === 1 && !String(list[0].prompt || '').trim()
  const seen = new Set(list.map((s) => normalizePrompt(s.prompt)).filter(Boolean))
  const room = max - (replaceBlank ? 0 : list.length)
  const toAdd = []
  for (const c of candidates) {
    if (toAdd.length >= room) break
    const key = normalizePrompt(c.prompt)
    if (!key || seen.has(key)) continue
    seen.add(key)
    toAdd.push(c)
  }
  return { toAdd, replaceBlank }
}

// Build the scenarios of a pack from the i18n function `t`. "general" is built by the view
// (it depends on the team members), so it returns [] here.
export function buildPackScenarios(packId, t) {
  if (packId === 'general') return []
  const out = []
  for (let i = 1; i <= SCENARIOS_PER_PACK; i++) {
    const base = `lab.packs.${packId}.s${i}_`
    out.push({ name: t(base + 'name'), prompt: t(base + 'prompt'), criteria: t(base + 'criteria') })
  }
  return out
}

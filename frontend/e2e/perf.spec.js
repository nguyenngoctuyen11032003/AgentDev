/* global process */
// UI performance baseline: `npm run perf`. Records numbers into docs/audit/perf-baseline.{json,md}
// (each run is appended to the json, the md is regenerated). Loose budgets only; no model calls.
// Measures a production build served by `vite preview` (PERF_DEV=1 for the dev server instead).
import fs from 'node:fs'
import path from 'node:path'
import { test, expect } from '@playwright/test'
import {
  startServer, measureLoad, measureHeapExact, literalYaml, uploadWorkflow, removeWorkflow, startFpsProbe, stopFpsProbe,
  SMALL_FILE, BIG_FILE, repoDir, round,
} from './helpers/perf.js'

// Loose budgets, ~50% above the first measured baseline (docs/audit/perf-baseline.md). Not tight gates.
const BUDGET = {
  loadMs: 150,
  lcpMs: 3000, // run-to-run outliers seen (launch 684 vs 2696 ms)
  jsKBPerRoute: 1800, // raw
  domNodes1000MessagesInitial: 5000, // default window; fully expanded is only reported (alert)
  dragAvgFpsMin: 20,
  heapGrowthRatio: 1.5, // heap after cycle 2 / after cycle 1 (same page)
}

const PAGES = [
  { name: 'home', url: '/' },
  { name: 'tutorial', url: '/tutorial' },
  { name: 'workflow', url: `/workflows/${SMALL_FILE}` },
  { name: 'launch', url: '/launch' },
  { name: 'lab', url: '/lab' },
  { name: 'settings-general', url: '/settings/general' },
  { name: 'settings-connections', url: '/settings/connections' },
  { name: 'settings-skills', url: '/settings/skills' },
  { name: 'batch-run', url: '/batch-run' },
]
const CYCLE = PAGES.slice(0, 8)

const OUT_JSON = path.join(repoDir, 'docs', 'audit', 'perf-baseline.json')
const OUT_MD = path.join(repoDir, 'docs', 'audit', 'perf-baseline.md')

let server
const result = { startedAt: new Date().toISOString(), loads: [], messages: null, drag: null, heap: null }

test.describe.configure({ mode: 'serial' })
test.use({ trace: 'off' }) // tracing would distort the numbers

test.beforeAll(async ({ request }) => {
  server = await startServer()
  result.mode = server.mode
  await uploadWorkflow(request, SMALL_FILE, literalYaml('zz_perf_small', 3))
  await uploadWorkflow(request, BIG_FILE, literalYaml('zz_perf_200', 200))
})

test.afterAll(async ({ request }) => {
  await removeWorkflow(request, SMALL_FILE)
  await removeWorkflow(request, BIG_FILE)
  await server?.stop()
  writeOutputs(result)
})

test('a/b. cold load time and JS/CSS size per page', async ({ browser }) => {
  for (const p of PAGES) {
    const r = await measureLoad(browser, server.base, p.url)
    result.loads.push({ page: p.name, ...r })
    expect(r.loadMs, `${p.name} load`).toBeLessThan(BUDGET.loadMs)
    expect(r.lcpMs, `${p.name} LCP`).toBeLessThan(BUDGET.lcpMs)
    expect(r.js.rawKB, `${p.name} js`).toBeLessThan(BUDGET.jsKBPerRoute)
  }
})

test('c. DOM nodes when opening a session with 1000 messages (mocked socket)', async ({ page }) => {
  const sessionId = 'zz-perf-session'
  await page.routeWebSocket(/\/ws\?/, (ws) => {
    const t0 = Date.now() - 3_600_000
    const messages = []
    for (let i = 0; i < 500; i++) {
      const ts = new Date(t0 + i * 2000).toISOString()
      messages.push({ type: 'user_message', data: { text: `Question ${i}: please summarise item ${i}.`, timestamp: ts } })
      messages.push({ type: 'lead_note_reply', data: { note_id: `n${i}`, kind: 'status', lead: 'Lead', text: `Answer ${i}.\n\n- point one\n- point two\n\n**done** ${'lorem ipsum '.repeat(8)}`, timestamp: ts } })
    }
    ws.send(JSON.stringify({ type: 'connection', data: { session_id: sessionId, resumed: true } }))
    ws.send(JSON.stringify({ type: 'batch', data: messages }))
    ws.send(JSON.stringify({ type: 'session_resumed', data: { session_id: sessionId, yaml_file: SMALL_FILE, status: 'completed', projects: [] } }))
    ws.onMessage(() => {})
  })
  const t0 = Date.now()
  await page.goto(`${server.base}/launch?workflow=${SMALL_FILE}&session=${sessionId}`)
  await page.waitForSelector('.chat-message-item', { state: 'attached', timeout: 60_000 })
  const firstBubbleMs = Date.now() - t0
  await page.waitForTimeout(1500)
  const count = () => page.evaluate(() => ({
    dom: document.querySelectorAll('*').length,
    items: document.querySelectorAll('.chat-message-item').length,
  }))
  const initial = await count()
  // Worst case: expand every older message
  let clicks = 0
  while ((await page.locator('.chat-older-btn').count()) && clicks < 40) {
    await page.locator('.chat-older-btn').first().click()
    await page.waitForTimeout(150)
    clicks++
  }
  await page.waitForTimeout(500)
  const expanded = await count()
  result.messages = { sentMessages: 1000, firstBubbleMs, initial, expanded, showOlderClicks: clicks }
  expect(initial.dom).toBeLessThan(BUDGET.domNodes1000MessagesInitial)
})

test('d. canvas drag FPS with a 200-node workflow', async ({ page }) => {
  await page.goto(`${server.base}/workflows/${BIG_FILE}`)
  await page.waitForSelector('.vue-flow__node', { timeout: 60_000 })
  await page.waitForTimeout(2500)
  const nodes = await page.locator('.vue-flow__node').count()
  const total = await page.evaluate(() => document.querySelectorAll('*').length)
  // Find an empty spot of the canvas pane to grab
  const start = await page.evaluate(() => {
    const pane = document.querySelector('.vue-flow__pane')
    const r = pane.getBoundingClientRect()
    for (let y = r.top + 20; y < r.bottom - 20; y += 25) {
      for (let x = r.left + 20; x < r.right - 20; x += 25) {
        const el = document.elementFromPoint(x, y)
        if (el && el.classList.contains('vue-flow__pane')) return { x, y }
      }
    }
    return null
  })
  expect(start, 'empty canvas spot').not.toBeNull()
  await page.mouse.move(start.x, start.y)
  await page.mouse.down()
  await startFpsProbe(page)
  const t0 = Date.now()
  let i = 0
  while (Date.now() - t0 < 3000) {
    const a = (i++ / 20) * Math.PI
    await page.mouse.move(start.x + Math.cos(a) * 120, start.y + Math.sin(a) * 120)
    await page.waitForTimeout(8)
  }
  const fps = await stopFpsProbe(page)
  await page.mouse.up()
  result.drag = { workflowNodes: 200, renderedNodes: nodes, domNodes: total, dragMs: Date.now() - t0, mouseMoves: i, ...fps }
  expect(fps.avgFps).toBeGreaterThan(BUDGET.dragAvgFpsMin)
})

test('e. JS heap across 16 navigations (forced GC)', async ({ page }) => {
  await page.goto(`${server.base}${CYCLE[0].url}`)
  await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})
  await page.waitForTimeout(1000)
  const series = [{ step: 0, page: CYCLE[0].name, ...(await measureHeapExact(page)) }]
  for (let n = 1; n <= 16; n++) {
    const target = CYCLE[n % CYCLE.length]
    await page.evaluate((url) => document.querySelector('#app').__vue_app__.config.globalProperties.$router.push(url), target.url)
    await page.waitForTimeout(1200)
    series.push({ step: n, page: target.name, ...(await measureHeapExact(page)) })
  }
  const first = series[0].usedMB
  const last = series[series.length - 1].usedMB
  // Step 8 and 16 are both "home" after a full cycle (route chunks and caches already warm): the drift
  // between them is the leak signal; first -> last also contains one-off lazy module loading.
  const steady = round(series[16].usedMB / series[8].usedMB, 2)
  result.heap = { series, firstMB: first, lastMB: last, ratio: round(last / first, 2), steadyFirstMB: series[8].usedMB, steadyLastMB: series[16].usedMB, steadyRatio: steady }
  expect(steady).toBeLessThan(BUDGET.heapGrowthRatio)
})

function alerts(r) {
  const out = []
  for (const l of r.loads) {
    if (l.domNodes > 5000) out.push(`${l.page}: ${l.domNodes} DOM nodes on load`)
    if (l.js.rawKB > 1000) out.push(`${l.page}: ${l.js.rawKB} KB raw JS`)
  }
  if (r.messages?.expanded.dom > 5000) out.push(`1000 messages fully expanded: ${r.messages.expanded.dom} DOM nodes (initial window: ${r.messages.initial.dom})`)
  if (r.drag && r.drag.avgFps < 30) out.push(`canvas drag with 200 nodes: ${r.drag.avgFps} fps avg, ${r.drag.framesOver50ms} frames >50 ms`)
  if (r.heap && r.heap.steadyRatio > 1.15) out.push(`heap grew x${r.heap.steadyRatio} between navigation 8 and 16 (${r.heap.steadyFirstMB} -> ${r.heap.steadyLastMB} MB): possible leak`)
  return out
}

function writeOutputs(r) {
  if (!r.loads.length) return
  r.finishedAt = new Date().toISOString()
  let runs = []
  try { runs = JSON.parse(fs.readFileSync(OUT_JSON, 'utf8')).runs || [] } catch { /* first run */ }
  if (process.env.PERF_RESET) runs = []
  runs.push({ ...r, alerts: alerts(r) })
  fs.mkdirSync(path.dirname(OUT_JSON), { recursive: true })
  fs.writeFileSync(OUT_JSON, JSON.stringify({ runs }, null, 2))
  fs.writeFileSync(OUT_MD, renderMd(runs))
}

const fmt = (vals) => vals.join(' / ')

function renderMd(runs) {
  const last = runs[runs.length - 1]
  const L = []
  L.push('# UI performance baseline', '')
  L.push(`Generated by \`npm run perf\` (frontend/e2e/perf.spec.js). ${runs.length} run(s); cells show run1 / run2 ... to show variance.`)
  L.push(`Server: ${last.mode}. Chromium headless, cold cache per page, backend on localhost. Numbers are measurements, not gates.`, '')
  L.push('## a/b. Page load and bundle size (cold cache)', '')
  L.push('| Page | DCL ms | Load ms | LCP ms | DOM nodes | JS files | JS raw KB | JS transferred KB | CSS raw KB | API calls |')
  L.push('|---|---|---|---|---|---|---|---|---|---|')
  for (const l of last.loads) {
    const all = runs.map((r) => r.loads.find((x) => x.page === l.page)).filter(Boolean)
    const c = (f) => fmt(all.map(f))
    L.push(`| ${l.page} (${l.url}) | ${c((x) => x.domContentLoadedMs)} | ${c((x) => x.loadMs)} | ${c((x) => x.lcpMs)} | ${l.domNodes} | ${l.js.files} | ${l.js.rawKB} | ${l.js.transferredKB} | ${l.css.rawKB} | ${l.apiRequests} |`)
  }
  L.push('', 'Sizes cover same-origin requests during the navigation (route chunks load lazily; API responses excluded). Transferred = bytes on the wire (vite preview does not compress, so about raw plus headers).', '')
  L.push('## c. Session with 1,000 messages (mocked WebSocket replay, 500 user + 500 lead bubbles)', '')
  L.push('| Run | First bubble ms | DOM nodes (initial window) | Message items | DOM nodes (all expanded) | Message items | Older-button clicks |')
  L.push('|---|---|---|---|---|---|---|')
  runs.forEach((r, i) => { const m = r.messages; if (m) L.push(`| ${i + 1} | ${m.firstBubbleMs} | ${m.initial.dom} | ${m.initial.items} | ${m.expanded.dom} | ${m.expanded.items} | ${m.showOlderClicks} |`) })
  L.push('', 'The chat renders only the latest window and reveals older messages on demand ("show older"); "all expanded" is the worst case.', '')
  L.push('## d. Canvas drag, 200-node workflow (3 s mouse drag)', '')
  L.push('| Run | Rendered nodes | DOM nodes | Avg FPS | p95 frame ms | Max frame ms | Frames >50 ms | Frames |')
  L.push('|---|---|---|---|---|---|---|---|')
  runs.forEach((r, i) => { const d = r.drag; if (d) L.push(`| ${i + 1} | ${d.renderedNodes} | ${d.domNodes} | ${d.avgFps} | ${d.p95FrameMs} | ${d.maxFrameMs} | ${d.framesOver50ms} | ${d.frames} |`) })
  L.push('', '## e. JS heap over 16 SPA navigations (forced GC each step, CDP Runtime.getHeapUsage)', '')
  L.push('| Run | First MB (step 0) | Last MB (step 16) | Ratio | Steady drift: step 8 -> 16 MB | Steady ratio | Series (MB) |')
  L.push('|---|---|---|---|---|---|---|')
  runs.forEach((r, i) => { const h = r.heap; if (h) L.push(`| ${i + 1} | ${h.firstMB} | ${h.lastMB} | ${h.ratio} | ${h.steadyFirstMB} -> ${h.steadyLastMB} | ${h.steadyRatio} | ${h.series.map((s) => s.usedMB).join(', ')} |`) })
  L.push('', 'First -> last includes one-off lazy chunk loading (route code, i18n, caches); the steady drift compares the same page after cycle 1 and cycle 2. Navigation order: ' + Array.from({ length: 17 }, (_, n) => n).map((n) => CYCLE[n % CYCLE.length].name).join(' > '), '')
  L.push('## Alerts', '')
  const al = [...new Set(runs.flatMap((r) => r.alerts))]
  L.push(...(al.length ? al.map((a) => `- ${a}`) : ['- none (no page over 5k DOM nodes, no steady heap growth over x1.15, drag >= 30 fps)']), '')
  return L.join('\n')
}

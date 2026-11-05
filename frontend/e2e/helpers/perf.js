/* global process */
// Helpers for e2e/perf.spec.js: production preview server, cold page-load capture, request sizes,
// workflow seeding, FPS probe. Nothing here calls a model.
import { spawn, execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { API } from './workflow.js'

const here = path.dirname(fileURLToPath(import.meta.url))
export const frontendDir = path.resolve(here, '..', '..')
export const repoDir = path.resolve(frontendDir, '..')
export const distDir = path.resolve(frontendDir, 'e2e', 'artifacts', 'perf-dist')
export const PREVIEW_PORT = Number(process.env.PERF_PORT || 5180)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const up = async (url) => {
  try {
    return (await fetch(url, { signal: AbortSignal.timeout(2000) })).status < 500
  } catch {
    return false
  }
}

function killTree(child) {
  if (!child?.pid) return
  try {
    if (process.platform === 'win32') execFileSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
    else process.kill(child.pid, 'SIGTERM')
  } catch { /* already gone */ }
}

// Builds into e2e/artifacts/perf-dist (git-ignored) and serves it with `vite preview`.
// PERF_DEV=1 measures the dev server (E2E_WEB) instead. Returns { base, mode, stop }.
export async function startServer() {
  if (process.env.PERF_DEV) {
    return { base: process.env.E2E_WEB || 'http://localhost:5173', mode: 'vite dev server (unbundled, not production)', stop: async () => {} }
  }
  const vite = path.join(frontendDir, 'node_modules', 'vite', 'bin', 'vite.js')
  if (!process.env.PERF_SKIP_BUILD) {
    execFileSync(process.execPath, [vite, 'build', '--outDir', distDir, '--emptyOutDir'], { cwd: frontendDir, stdio: 'ignore' })
  }
  const base = `http://localhost:${PREVIEW_PORT}`
  if (await up(base)) throw new Error(`port ${PREVIEW_PORT} already in use; set PERF_PORT`)
  const child = spawn(process.execPath, [vite, 'preview', '--outDir', distDir, '--port', String(PREVIEW_PORT), '--strictPort'], {
    cwd: frontendDir,
    stdio: 'ignore',
    windowsHide: true,
  })
  for (let i = 0; i < 60 && !(await up(base)); i++) await sleep(500)
  if (!(await up(base))) {
    killTree(child)
    throw new Error('vite preview did not start')
  }
  return { base, mode: 'production build (vite build + vite preview, no compression)', stop: async () => killTree(child) }
}

// Cold load of one URL in a fresh context (empty cache). Returns timings and per-type sizes.
export async function measureLoad(browser, base, url, { settleMs = 1500 } = {}) {
  const context = await browser.newContext()
  const page = await context.newPage()
  const client = await context.newCDPSession(page)
  await client.send('Network.enable')
  const reqs = new Map()
  client.on('Network.responseReceived', (e) => reqs.set(e.requestId, { url: e.response.url, type: e.type, status: e.response.status, raw: 0, transferred: 0 }))
  client.on('Network.dataReceived', (e) => { const r = reqs.get(e.requestId); if (r) r.raw += e.dataLength })
  client.on('Network.loadingFinished', (e) => { const r = reqs.get(e.requestId); if (r) r.transferred = e.encodedDataLength })
  await page.addInitScript(() => {
    window.__lcp = 0
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) window.__lcp = entry.startTime
      }).observe({ type: 'largest-contentful-paint', buffered: true })
    } catch { /* unsupported */ }
  })
  try {
    await page.goto(base + url, { waitUntil: 'load' })
    await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})
    await page.waitForTimeout(settleMs)
    const t = await page.evaluate(() => {
      const nav = performance.getEntriesByType('navigation')[0]
      return { dcl: nav.domContentLoadedEventEnd, load: nav.loadEventEnd, lcp: window.__lcp, dom: document.querySelectorAll('*').length }
    })
    const own = [...reqs.values()].filter((r) => r.url.startsWith(base))
    const sum = (list, key) => list.reduce((a, r) => a + r[key], 0)
    const bucket = (ext) => {
      const list = own.filter((r) => ext.test(new URL(r.url).pathname))
      return { files: list.length, rawKB: round(sum(list, 'raw') / 1024), transferredKB: round(sum(list, 'transferred') / 1024) }
    }
    return {
      url,
      domContentLoadedMs: round(t.dcl),
      loadMs: round(t.load),
      lcpMs: round(t.lcp),
      domNodes: t.dom,
      js: bucket(/\.m?js$/),
      css: bucket(/\.css$/),
      apiRequests: [...reqs.values()].filter((r) => /\/api\//.test(r.url)).length,
    }
  } finally {
    await client.detach().catch(() => {})
    await context.close()
  }
}

export const round = (n, d = 1) => Math.round(n * 10 ** d) / 10 ** d

export const SMALL_FILE = 'zz_perf_small.yaml'
export const BIG_FILE = 'zz_perf_200.yaml'

export const literalYaml = (id, count) => {
  const nodes = []
  const edges = []
  for (let i = 0; i < count; i++) {
    nodes.push(`  - id: N${i}\n    type: literal\n    description: perf node ${i}\n    config:\n      role: assistant\n      content: node ${i}`)
    if (i > 0) edges.push(`  - from: N${Math.floor((i - 1) / 2)}\n    to: N${i}`) // binary tree: wide and deep
  }
  return `version: 0.4.0\nvars: {}\ngraph:\n  id: ${id}\n  description: perf fixture (literal nodes, no model calls)\n  log_level: INFO\n  is_majority_voting: false\n  start:\n  - N0\n  end:\n  - N${count - 1}\n  nodes:\n${nodes.join('\n')}\n  edges:\n${edges.join('\n')}\n`
}

export async function uploadWorkflow(request, file, content) {
  await request.delete(`${API}/api/workflows/${file}/delete`).catch(() => {})
  const res = await request.post(`${API}/api/workflows/upload/content`, { data: { filename: file, content } })
  if (!res.ok()) throw new Error(`upload ${file} failed: ${res.status()} ${await res.text()}`)
}
export const removeWorkflow = (request, file) => request.delete(`${API}/api/workflows/${file}/delete`).catch(() => {})

// requestAnimationFrame probe: call start() before the gesture and stop() after it.
export async function startFpsProbe(page) {
  await page.evaluate(() => {
    const deltas = []
    let last = performance.now()
    let alive = true
    const tick = (now) => {
      deltas.push(now - last)
      last = now
      if (alive) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
    window.__fps = { deltas, stop: () => { alive = false } }
  })
}
export async function stopFpsProbe(page) {
  const deltas = await page.evaluate(() => { window.__fps.stop(); return window.__fps.deltas.slice(1) })
  const total = deltas.reduce((a, b) => a + b, 0)
  const sorted = [...deltas].sort((a, b) => a - b)
  return {
    frames: deltas.length,
    avgFps: round((deltas.length / total) * 1000),
    p95FrameMs: round(sorted[Math.floor(sorted.length * 0.95)] || 0),
    maxFrameMs: round(sorted[sorted.length - 1] || 0),
    framesOver50ms: deltas.filter((d) => d > 50).length,
  }
}

export function writeReport(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, JSON.stringify(data, null, 2))
}

// Exact JS heap after a forced GC. performance.memory (used by helpers/heap.js) is bucketed by Chrome
// and showed a flat 9.5 MB, so this reads the V8 heap usage straight from CDP.
export async function measureHeapExact(page) {
  const client = await page.context().newCDPSession(page)
  try {
    await client.send('HeapProfiler.collectGarbage')
    await client.send('HeapProfiler.collectGarbage')
    const { usedSize, totalSize } = await client.send('Runtime.getHeapUsage')
    return { usedMB: round(usedSize / 1048576, 2), totalMB: round(totalSize / 1048576, 2) }
  } finally {
    await client.detach().catch(() => {})
  }
}

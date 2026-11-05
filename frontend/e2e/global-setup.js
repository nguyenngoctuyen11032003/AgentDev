/* global process */
// Starts only the servers that are not already answering, creates the fake workflow, and returns a
// teardown that deletes everything the suite created and kills only the processes it started.
import { spawn, execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { request } from '@playwright/test'
import { API, createWorkflow, deleteWorkflow, WORKFLOW_FILE } from './helpers/workflow.js'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendDir = path.resolve(here, '..')
const backendDir = path.resolve(frontendDir, '..', 'backend')
const WEB = process.env.E2E_WEB || 'http://localhost:5173'
const warehouseDir = path.resolve(frontendDir, '..', 'storage', 'warehouse')
const started = []

async function up(url) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(3000) })
    return res.status < 500
  } catch {
    return false
  }
}

async function waitFor(url, label, ms = 120_000) {
  const end = Date.now() + ms
  while (Date.now() < end) {
    if (await up(url)) return
    await new Promise((r) => setTimeout(r, 1000))
  }
  throw new Error(`${label} did not answer at ${url} within ${ms / 1000}s`)
}

function start(label, command, args, cwd, env = {}) {
  const child = spawn(command, args, {
    cwd,
    env: { ...process.env, ...env },
    shell: true,
    stdio: 'ignore',
    windowsHide: true,
  })
  started.push({ label, child })
  console.log(`[e2e] started ${label} (pid ${child.pid})`)
}

function killTree(child) {
  if (!child.pid) return
  try {
    if (process.platform === 'win32') execFileSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
    else process.kill(-child.pid, 'SIGTERM')
  } catch { /* already gone */ }
}

export default async function globalSetup() {
  if (await up(`${API}/health`)) console.log('[e2e] reusing backend')
  else {
    start('backend', 'uv', ['run', 'python', 'main.py', '--port', new URL(API).port || '6400'], backendDir)
    await waitFor(`${API}/health`, 'backend')
  }
  if (await up(WEB)) console.log('[e2e] reusing frontend')
  else {
    start('frontend', 'npx', ['vite', '--port', new URL(WEB).port || '5173', '--strictPort'], frontendDir, { VITE_API_BASE_URL: API })
    await waitFor(WEB, 'frontend')
  }

  const api = await request.newContext()
  await createWorkflow(api)
  await api.dispose()

  return async () => {
    const ctx = await request.newContext()
    try {
      // Sessions the suite made (every one runs the fake workflow). A session still waiting on the gate is active: cancel by deleting later.
      const list = await (await ctx.get(`${API}/api/sessions`)).json().catch(() => ({ sessions: [] }))
      for (const s of (list.sessions || []).filter((x) => x.yaml_file === WORKFLOW_FILE)) {
        const res = await ctx.delete(`${API}/api/sessions/${s.session_id}`).catch(() => null)
        if (!res || !res.ok()) console.log(`[e2e] could not delete session ${s.session_id} (${res?.status()})`)
        else fs.rmSync(path.join(warehouseDir, `session_${s.session_id}`), { recursive: true, force: true }) // the run's temp files
      }
      await deleteWorkflow(ctx)
    } finally {
      await ctx.dispose()
      for (const { label, child } of started.reverse()) {
        killTree(child)
        console.log(`[e2e] stopped ${label}`)
      }
    }
  }
}

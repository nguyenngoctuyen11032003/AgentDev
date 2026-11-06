import { readFileSync } from 'node:fs'
import { expect } from './fixture.js'
import { WORKFLOW_FILE } from './workflow.js'

// Shared Lab mocks (lab.spec.js, lab-layers-axe.spec.js): the judge and the scenario writer spend model tokens,
// so evaluate/generate/jobs are always mocked. The configuration check is free and hits the real backend.
export const JOB = JSON.parse(readFileSync(new URL('./lab-job.json', import.meta.url), 'utf8'))
export const RUNNING = { ...JOB, status: 'running', done: 0, judged: 0, passed: 0, verdict: '', results: [], finished_at: null }


export async function mockLabSpend(page, { evaluateStatus = 202, job = JOB } = {}) {
  const calls = { evaluate: [], generate: 0 }
  await page.route('**/api/lab/evaluate', (route) => {
    calls.evaluate.push(route.request().postDataJSON())
    if (evaluateStatus !== 202) return route.fulfill({ status: evaluateStatus, json: { detail: 'Add at least one test scenario' } })
    return route.fulfill({ status: 202, json: RUNNING })
  })
  await page.route(`**/api/lab/jobs/${JOB.id}`, (route) => route.fulfill({ json: job }))
  await page.route(`**/api/lab/jobs/${JOB.id}/products`, (route) => route.fulfill({ json: { runs: [] } }))
  await page.route(`**/api/lab/jobs/${JOB.id}/runs/*/files`, (route) => route.fulfill({ json: { files: [] } }))
  await page.route('**/api/lab/generate', (route) => {
    calls.generate += 1
    return route.fulfill({ json: { scenarios: [{ name: 'AI one', prompt: 'Chao ban, ban la ai?', criteria: 'Tra loi ngan' }, { name: 'AI two', prompt: 'Viet 3 dong', criteria: '' }] } })
  })
  return calls
}

// Pages whose test mocks /api/lab/platform-fixes itself (lab-platform-fixes.spec.js).
const fixesMocked = new WeakSet()

/** Mock the machine-wide platform-fix list (and its sub-routes) with `handler(route)`; pickWorkflow keeps it. */
export async function mockPlatformFixes(page, handler) {
  fixesMocked.add(page)
  await page.route(/\/api\/lab\/platform-fixes(\/.*)?(\?.*)?$/, handler)
}

export async function pickWorkflow(page) {
  // Lab tests that are not about platform fixes see none, whatever worktrees this machine has.
  if (!fixesMocked.has(page)) await mockPlatformFixes(page, (route) => route.fulfill({ json: { items: [] } }))
  await page.goto('/lab')
  await page.locator('#lab-workflow-picker').selectOption(WORKFLOW_FILE)
}

export const F_WORKFLOW = { scenario: 0, severity: 'fail', layer: 'workflow', detail: 'Vong lap khong dung', fix: 'Them dieu kien dung' }
export const F_ENV = { scenario: 0, severity: 'warn', layer: 'environment', error_kind: 'model_call', detail: 'Bi gioi han 429', fix: 'Cho het gioi han' }
export const F_PLATFORM = { scenario: 0, severity: 'fail', layer: 'platform', error_kind: 'engine_exception', detail: 'AttributeError trong engine', fix: 'Gui bao cao' }
export const F_SCENARIO = { scenario: 0, severity: 'warn', layer: 'scenario', detail: 'Giam khao khong nhat quan', fix: 'Xem lai tieu chi' }
export const ENV_HINTS = [{ code: 'rate_limit', detail: 'Tai khoan dang bi gioi han', fix: 'Cho vai phut roi chay lai', scenario: 0 }]
export const PLATFORM_REPORT = '# Platform report\n\nAttributeError: NoneType has no attribute x'
export const JOB_MIXED = {
  ...JOB,
  verdict: 'not_ready',
  findings: [F_SCENARIO, F_PLATFORM, F_ENV, F_WORKFLOW],
  layers: { workflow: 1, platform: 1, environment: 1, scenario: 1 },
  needs_workflow_fix: true,
  fix_brief: 'E2E brief: sua vong lap',
  platform_report: PLATFORM_REPORT,
  environment_hints: ENV_HINTS
}
export const JOB_NO_WORKFLOW = {
  ...JOB,
  verdict: 'not_ready',
  findings: [F_ENV, F_SCENARIO],
  layers: { workflow: 0, platform: 0, environment: 1, scenario: 1 },
  needs_workflow_fix: false,
  fix_brief: '',
  environment_hints: ENV_HINTS
}
export const FIX_INFO = {
  enabled: true,
  // Same codes as backend/agentdev/api/services/platform_fix.py; the UI translates by code and falls back to `text`.
  steps: [
    { code: 'write_brief', text: 'Write PLATFORM_FIX.md in that worktree' },
    { code: 'future_step', text: 'Server-only step text' }
  ],
  forbidden: [{ path: 'backend/agentdev/api/routes/lab.py', kind: 'self', text: 'Lab routes' }],
  gates: [{ code: 'full_tests', command: 'cd backend && uv run pytest -q', text: 'All backend tests pass' }]
}

export async function runJob(page, job) {
  await mockLabSpend(page, { job })
  // These tests are about the diagnosis, not step 1: a failing config item (no CLI account on this machine)
  // must not block the mocked run, so the real check answer is kept but its failures are relaxed to warnings.
  await page.route('**/api/lab/check', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    for (const c of body.checks || []) if (c.status === 'fail') c.status = 'warn'
    return route.fulfill({ response, json: body })
  })
  await pickWorkflow(page)
  await page.locator('.scenario').first().locator('textarea').first().fill('chạy thử e2e')
  const run = page.getByRole('button', { name: 'Bắt đầu chạy thử' })
  await expect(run).toBeEnabled({ timeout: 30_000 })
  await run.click()
  await expect(page.locator('.diagnosis')).toBeVisible()
}

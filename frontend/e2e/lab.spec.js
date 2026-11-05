import { readFileSync } from 'node:fs'
import { test, expect } from './helpers/fixture.js'
import { WORKFLOW_FILE } from './helpers/workflow.js'

// The real Lab judge and AI scenario writer spend model tokens, so evaluate/generate/jobs are mocked here.
// The configuration check is free and runs against the real backend.
const JOB = JSON.parse(readFileSync(new URL('./helpers/lab-job.json', import.meta.url), 'utf8'))
const RUNNING = { ...JOB, status: 'running', done: 0, judged: 0, passed: 0, verdict: '', results: [], finished_at: null }

test.beforeEach(async ({ page }) => { await page.setViewportSize({ width: 1440, height: 900 }) })

async function mockLabSpend(page, { evaluateStatus = 202 } = {}) {
  const calls = { evaluate: [], generate: 0 }
  await page.route('**/api/lab/evaluate', (route) => {
    calls.evaluate.push(route.request().postDataJSON())
    if (evaluateStatus !== 202) return route.fulfill({ status: evaluateStatus, json: { detail: 'Add at least one test scenario' } })
    return route.fulfill({ status: 202, json: RUNNING })
  })
  await page.route(`**/api/lab/jobs/${JOB.id}`, (route) => route.fulfill({ json: JOB }))
  await page.route(`**/api/lab/jobs/${JOB.id}/products`, (route) => route.fulfill({ json: { runs: [] } }))
  await page.route(`**/api/lab/jobs/${JOB.id}/runs/*/files`, (route) => route.fulfill({ json: { files: [] } }))
  await page.route('**/api/lab/generate', (route) => {
    calls.generate += 1
    return route.fulfill({ json: { scenarios: [{ name: 'AI one', prompt: 'Chao ban, ban la ai?', criteria: 'Tra loi ngan' }, { name: 'AI two', prompt: 'Viet 3 dong', criteria: '' }] } })
  })
  return calls
}

async function pickWorkflow(page) {
  await page.goto('/lab')
  await page.locator('#lab-workflow-picker').selectOption(WORKFLOW_FILE)
}

test('lab: without a workflow the page explains how it works', async ({ page }) => {
  await page.goto('/lab')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Phòng thí nghiệm')
  await expect(page.locator('.intro')).toContainText('Chọn một quy trình ở trên để bắt đầu.')
  await expect(page.locator('.intro-step')).toHaveCount(2)
})

test('lab: picking a workflow runs the free configuration check and lists its items', async ({ page }) => {
  await pickWorkflow(page)
  await expect(page.locator('.check-item').first()).toBeVisible()
  expect(await page.locator('.check-item').count()).toBeGreaterThan(2)
  await expect(page.locator('.chips .chip').first()).toBeVisible()
  await expect(page.locator('.metrics')).toBeVisible()
})

test('lab: run is blocked without a prompt, then a literal scenario runs and shows the verdict and answer', async ({ page }) => {
  const calls = await mockLabSpend(page)
  await pickWorkflow(page)
  const run = page.getByRole('button', { name: 'Bắt đầu chạy thử' })
  await expect(page.locator('.check-item').first()).toBeVisible()
  await expect(run).toBeDisabled()

  const first = page.locator('.scenario').first()
  await first.locator('textarea').first().fill('chạy thử e2e')
  await expect(run).toBeEnabled({ timeout: 30_000 })
  await expect(page.locator('.cost-estimate')).toContainText('1 kịch bản')
  await run.click()

  await expect(page.locator('.verdict')).toBeVisible()
  await expect(page.locator('.verdict')).toContainText('100')
  await page.locator('details.run').first().locator('summary').click()
  await expect(page.locator('details.run .answer')).toContainText('E2E FINISHED')
  expect(calls.evaluate).toHaveLength(1)
  expect(calls.evaluate[0].yaml_file).toBe(WORKFLOW_FILE)
  expect(calls.evaluate[0].scenarios[0].prompt).toBe('chạy thử e2e')
})

test('lab: AI scenario generator (mocked) fills scenarios, which can be removed', async ({ page }) => {
  const calls = await mockLabSpend(page)
  await pickWorkflow(page)
  await expect(page.locator('.scenario')).toHaveCount(1) // one empty draft; the generator replaces empty drafts
  await page.getByRole('button', { name: /AI tạo kịch bản theo quy trình/ }).click()
  await expect(page.locator('.scenario')).toHaveCount(2)
  expect(calls.generate).toBe(1)
  await expect(page.locator('.scenario textarea').first()).toHaveValue('Chao ban, ban la ai?')
  await page.locator('.scenario').first().getByRole('button', { name: /Xóa/ }).click()
  await expect(page.locator('.scenario')).toHaveCount(1)
})

test('lab: a failing generator shows an error with a hint instead of hanging', async ({ page, guard }) => {
  guard.allow(/api\/lab\/generate|Failed to load resource/)
  await page.route('**/api/lab/generate', (route) => route.fulfill({ status: 502, json: { detail: 'model unavailable' } }))
  await pickWorkflow(page)
  await page.getByRole('button', { name: /AI tạo kịch bản theo quy trình/ }).click()
  await expect(page.getByText(/model unavailable/).first()).toBeVisible()
  await expect(page.getByRole('button', { name: /AI tạo kịch bản theo quy trình/ })).toBeEnabled()
})

test('lab: workflow list load error is shown with a retry button', async ({ page, guard }) => {
  guard.allow(/api\/workflows|Failed to load resource/)
  await page.route('**/api/workflows', (route) => route.fulfill({ status: 500, json: { detail: 'boom' } }))
  await page.goto('/lab')
  await expect(page.locator('.intro-error')).toBeVisible()
  await expect(page.locator('.intro-error').getByRole('button', { name: 'Thử lại' })).toBeVisible()
})

test('Batch Run is a tab of the Lab; /batch-run deep link opens it', async ({ page }) => {
  await page.goto('/batch-run')
  await expect(page).toHaveURL(/\/lab\?.*tab=batch/)
  await expect(page.getByRole('tab', { name: /Excel\/CSV|batch/i })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('#lab-panel-batch .launch-view')).toBeVisible()
  // Back to scoring: keyboard on the tablist
  await page.getByRole('tab', { selected: true }).press('ArrowLeft')
  await expect(page).not.toHaveURL(/tab=batch/)
  await expect(page.locator('#lab-panel-batch')).toHaveCount(0)
  await expect(page.locator('#lab-panel-score')).toBeVisible()
  // No second entry point to /batch-run left in the Lab
  await expect(page.locator('a[href="/batch-run"]')).toHaveCount(0)
})

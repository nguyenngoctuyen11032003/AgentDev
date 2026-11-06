import { readFileSync } from 'node:fs'
import { test, expect } from './helpers/fixture.js'
import { WORKFLOW_FILE } from './helpers/workflow.js'

// A rerun of the failed scenarios after a fix (rerun_of + rerun_compare), opened the way the workflow
// assistant opens it: /lab?workflow=...&job=<new id>. Jobs are mocked; nothing runs or spends tokens.
const SOURCE = JSON.parse(readFileSync(new URL('./helpers/lab-job.json', import.meta.url), 'utf8'))
const RERUN = {
  ...SOURCE,
  id: 'e2elabrerun02',
  rerun_of: SOURCE.id,
  rerun_scenarios: [0],
  rerun_compare: {
    // Lower total cost but +30% per run: the backend flags cost per run, and so must the table.
    before: { pass_rate: 0, avg_seconds: 10, cost_usd: 0.04, done: 4 },
    after: { pass_rate: 1, avg_seconds: 11, cost_usd: 0.026, done: 2 },
    flags: { cost_usd: { was: 0.01, now: 0.013, per_run: true } }
  }
}

async function mockJobs(page) {
  for (const job of [SOURCE, RERUN]) {
    await page.route(`**/api/lab/jobs/${job.id}`, (route) => route.fulfill({ json: job }))
    await page.route(`**/api/lab/jobs/${job.id}/products`, (route) => route.fulfill({ json: { runs: [] } }))
    await page.route(`**/api/lab/jobs/${job.id}/runs/*/files`, (route) => route.fulfill({ json: { files: [] } }))
  }
}

test.beforeEach(async ({ page }) => { await page.setViewportSize({ width: 1440, height: 900 }) })

test('lab: a rerun job shows the before/after table with the worse metric marked', async ({ page }) => {
  await mockJobs(page)
  await page.goto(`/lab?workflow=${WORKFLOW_FILE}&job=${RERUN.id}`)

  const compare = page.locator('.rerun-compare')
  await expect(compare).toBeVisible()
  await expect(compare.getByRole('heading')).toContainText('Trước và sau khi sửa')
  // The job id is used once, then leaves the address bar.
  await expect(page).not.toHaveURL(/[?&]job=/)

  const rows = compare.locator('tbody tr')
  await expect(rows).toHaveCount(3)
  const cost = rows.filter({ hasText: 'Chi phí mỗi lượt' })
  await expect(cost).toHaveClass(/worse/)
  await expect(cost).toContainText('$0.010')
  await expect(cost).toContainText('$0.013')
  await expect(cost).toContainText('Kém hơn')
  for (const label of ['Tỷ lệ đạt', 'Thời gian trung bình']) {
    const row = rows.filter({ hasText: label })
    await expect(row).not.toHaveClass(/worse/)
    await expect(row).not.toContainText('Kém hơn')
  }
  await expect(rows.filter({ hasText: 'Tỷ lệ đạt' })).toContainText('100%')

  // Back to the source evaluation: it has no comparison of its own.
  await compare.getByRole('button', { name: 'Xem lần kiểm định gốc' }).click()
  await expect(page.locator('.rerun-compare')).toHaveCount(0)
})

test('lab: a ?job= link to a job of another workflow is not opened or remembered here', async ({ page }) => {
  const OTHER = { ...SOURCE, id: 'e2elabother03', workflow: 'zz_some_other_flow.yaml' }
  await page.route(`**/api/lab/jobs/${OTHER.id}`, (route) => route.fulfill({ json: OTHER }))
  await page.goto(`/lab?workflow=${WORKFLOW_FILE}&job=${OTHER.id}`)

  await expect(page.locator('.toast--warning')).toContainText('zz_some_other_flow')
  await expect(page).not.toHaveURL(/[?&]job=/)
  await expect(page.locator('section.results')).toHaveCount(0)
  const remembered = await page.evaluate((name) => sessionStorage.getItem(`agentdev.lab.job.${name}`), WORKFLOW_FILE)
  expect(remembered).toBeNull()
})

test('lab: a ?job= link to a missing job says so and falls back to the remembered job', async ({ page, guard }) => {
  guard.allow(/api\/lab\/jobs\/e2elabgone04|Failed to load resource/)
  await mockJobs(page)
  await page.route('**/api/lab/jobs/e2elabgone04', (route) =>
    route.fulfill({ status: 404, json: { detail: { code: 'lab_job_not_found', params: { job_id: 'e2elabgone04' } } } }))
  await page.addInitScript(([name, id]) => {
    sessionStorage.setItem(`agentdev.lab.job.${name}`, JSON.stringify({ id, submitted: [] }))
  }, [WORKFLOW_FILE, SOURCE.id])
  await page.goto(`/lab?workflow=${WORKFLOW_FILE}&job=e2elabgone04`)

  await expect(page.locator('.toast--error')).toContainText('e2elabgone04')
  await expect(page.locator('section.results')).toBeVisible()
})

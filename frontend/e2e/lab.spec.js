import { test, expect } from './helpers/fixture.js'
import { WORKFLOW_FILE } from './helpers/workflow.js'
import { F_SCENARIO, FIX_INFO, JOB, JOB_MIXED, JOB_NO_WORKFLOW, mockLabSpend, pickWorkflow, runJob } from './helpers/lab.js'

// The real Lab judge and AI scenario writer spend model tokens, so evaluate/generate/jobs are mocked here.
// The configuration check is free and runs against the real backend.

test.beforeEach(async ({ page }) => { await page.setViewportSize({ width: 1440, height: 900 }) })

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

// Findings by layer: only workflow findings ask the assistant for a fix; the other layers get their own guidance.

test('lab: findings are grouped by layer and the assistant fix appears with workflow findings', async ({ page }) => {
  await runJob(page, JOB_MIXED)
  const titles = page.locator('.diag-layer-title')
  await expect(titles).toHaveCount(4)
  await expect(titles.nth(0)).toContainText('Do quy trình')
  await expect(titles.nth(1)).toContainText('Do môi trường')
  await expect(titles.nth(2)).toContainText('Nghi lỗi của AgentDev')
  await expect(titles.nth(3)).toContainText('Do kịch bản hoặc giám khảo')
  await expect(page.locator('.layer-workflow')).toContainText('Vong lap khong dung')
  await expect(page.locator('.layer-environment .env-hints')).toContainText('Cho vai phut roi chay lai')
  await expect(page.getByRole('button', { name: 'Chỉnh sửa quy trình theo lỗi này' })).toBeVisible()
  await expect(page.locator('#lab-brief')).toHaveValue('E2E brief: sua vong lap')
  await expect(page.locator('.diag-unchanged')).toHaveCount(0)
  // Platform report: collapsed preview + copy
  await page.getByText('Xem báo cáo lỗi nền tảng').click()
  await expect(page.locator('.pf-pre')).toContainText('AttributeError')
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.getByRole('button', { name: 'Chép báo cáo nền tảng' }).click()
  await expect(page.locator('.pf-actions')).toContainText('Đã chép báo cáo')
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('AttributeError: NoneType')
})

test('lab: quality per criterion shows for the job and inside a run', async ({ page }) => {
  const dims = {
    requirements: { score: 5, note: 'Thieu trang dang nhap' },
    correctness: { score: 8, note: '' },
    craft: { score: 4, note: 'Con TODO trong code' },
    verification: { score: 7, note: '' },
    communication: { score: 9, note: '' },
    effort_fit: { score: 6, note: '' }
  }
  const run = {
    ...JOB.results[0],
    judge: { ...JOB.results[0].judge, dimensions: dims, domain: 'code', scope: 'large', missing: ['Thieu test'], fixes: ['Them node kiem thu'] },
    login: { needs_login: true, login_url: 'http://localhost:3000/login', credentials: [{ username: 'admin', password: 'Admin@123', source: 'README.md' }] }
  }
  // One finding so runJob sees the diagnosis section; the run made a file, so opening it shows the product + login.
  const job = {
    ...JOB,
    results: [run],
    findings: [F_SCENARIO],
    layers: { workflow: 0, platform: 0, environment: 0, scenario: 1 },
    quality: { runs: 1, domain: 'code', scope: 'large', dimensions: { requirements: 5, correctness: 8, craft: 4, verification: 7, communication: 9, effort_fit: 6 }, weak: ['craft', 'requirements', 'effort_fit'], poor: ['craft'] }
  }
  await runJob(page, job)
  await page.route(`**/api/lab/jobs/${JOB.id}/runs/*/files`, (route) => route.fulfill({ json: { available: true, files: [{ path: 'README.md', size: 20 }] } }))
  await page.route(`**/api/lab/jobs/${JOB.id}/runs/*/file?*`, (route) => route.fulfill({ contentType: 'text/plain', body: '# Demo app' }))
  const summary = page.locator('.job-quality')
  await expect(summary).toContainText('Chất lượng theo tiêu chí')
  await expect(summary).toContainText('Lập trình')
  await expect(summary).toContainText('Việc lớn')
  await expect(summary.locator('.quality-row.low')).toContainText('Chất lượng chuyên môn')
  await page.locator('details.run').first().locator('summary').click()
  const inRun = page.locator('details.run .quality')
  await expect(inRun).toContainText('Con TODO trong code')
  await expect(inRun).toContainText('Thieu test')
  await expect(inRun).toContainText('Them node kiem thu')
  const login = page.locator('details.run .login-box')
  await expect(login).toContainText('Tài khoản đăng nhập để xem thử')
  await expect(login).toContainText('admin')
  await expect(login).toContainText('Admin@123')
  await expect(login).toContainText('lấy từ README.md')
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await login.getByRole('button', { name: 'Chép mật khẩu' }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('Admin@123')
})

test('lab: without workflow findings there is no assistant fix, only guidance', async ({ page }) => {
  await runJob(page, JOB_NO_WORKFLOW)
  await expect(page.locator('.diag-unchanged')).toContainText('Quy trình không cần sửa')
  await expect(page.locator('.diag-layer-title')).toHaveCount(2)
  await expect(page.locator('.layer-workflow')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Chỉnh sửa quy trình theo lỗi này' })).toHaveCount(0)
  await expect(page.locator('#lab-brief')).toHaveCount(0)
  await expect(page.locator('.layer-platform')).toHaveCount(0)
})

test('lab: platform fix dialog needs the checkbox and the password, shows errors and the prepared branch', async ({ page, guard }) => {
  guard.allow(/platform-fix|Failed to load resource/)
  const posts = []
  await page.route('**/api/lab/platform-fix/info', (route) => route.fulfill({ json: FIX_INFO }))
  await page.route(`**/api/lab/jobs/${JOB.id}/platform-fix`, (route) => {
    const body = route.request().postDataJSON()
    posts.push(body)
    if (body.password !== 'right') return route.fulfill({ status: 403, json: { detail: { code: 'bad_password', message: 'bad password', params: { attempts_left: 4 } } } })
    return route.fulfill({
      json: {
        branch: 'platform-fix/e2elabjob0001',
        worktree: 'D:/tmp/agentdev-platform-fix',
        brief_file: 'PLATFORM_FIX.md',
        actions: [
          { code: 'created_branch', text: 'Created branch', params: { branch: 'platform-fix/e2elabjob0001', head: '0123456789abcdef' } }
        ],
        next_steps: [{ code: 'open_worktree', text: 'Open the worktree', params: { path: 'D:/tmp/agentdev-platform-fix' } }]
      }
    })
  })
  await runJob(page, JOB_MIXED)
  const request = page.getByRole('button', { name: 'Yêu cầu sửa mã nguồn…' })
  await request.click()
  const dialog = page.getByRole('dialog', { name: 'Chuẩn bị sửa mã nguồn AgentDev' })
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText('Ghi PLATFORM_FIX.md vào worktree đó')
  await expect(dialog).toContainText('Server-only step text') // unknown code: server text as fallback
  await expect(dialog).toContainText('backend/agentdev/api/routes/lab.py · Chính tính năng này')
  await expect(dialog).toContainText('Toàn bộ test backend đạt: cd backend && uv run pytest -q')
  await expect(dialog).not.toContainText('All backend tests pass')

  const confirm = dialog.getByRole('button', { name: 'Xác nhận và chuẩn bị' })
  const password = dialog.locator('input[type="password"]')
  await expect(password).toHaveAttribute('autocomplete', 'off')
  await expect(confirm).toBeDisabled()
  await password.fill('wrong')
  await expect(confirm).toBeDisabled()
  await dialog.getByRole('checkbox').check()
  await expect(confirm).toBeEnabled()
  await confirm.click()
  await expect(dialog.getByRole('alert')).toContainText('Sai mật khẩu, còn 4 lần thử')
  await expect(password).toHaveValue('')
  expect(posts[0]).toEqual({ password: 'wrong', confirm: true })

  await password.fill('right')
  await confirm.click()
  await expect(dialog).toContainText('platform-fix/e2elabjob0001')
  await expect(dialog).toContainText('D:/tmp/agentdev-platform-fix')
  await expect(dialog).toContainText('Đã tạo nhánh platform-fix/e2elabjob0001 từ 0123456789')
  await expect(dialog).not.toContainText('0123456789abcdef')
  await expect(dialog).toContainText('Mở D:/tmp/agentdev-platform-fix và đọc PLATFORM_FIX.md')
  await expect(dialog).toContainText('Chưa có gì được gộp')

  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(request).toBeFocused()
})

test('lab: platform fix info load error shows a hint and a retry', async ({ page, guard }) => {
  guard.allow(/platform-fix|Failed to load resource/)
  let fail = true
  await page.route('**/api/lab/platform-fix/info', (route) =>
    fail ? route.fulfill({ status: 500, json: { detail: 'boom' } }) : route.fulfill({ json: FIX_INFO })
  )
  await runJob(page, JOB_MIXED)
  await page.getByRole('button', { name: 'Yêu cầu sửa mã nguồn…' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('alert')).toContainText('Kiểm tra máy chủ AgentDev')
  fail = false
  await dialog.getByRole('button', { name: 'Thử lại' }).click()
  await expect(dialog).toContainText('Ghi PLATFORM_FIX.md vào worktree đó')
})

test('Batch Run is a tab of the Lab; /batch-run deep link opens it', async ({ page }) => {
  await page.goto('/batch-run')
  await expect(page).toHaveURL(/\/lab\?.*tab=batch/)
  await expect(page.getByRole('tab', { name: /Excel\/CSV|batch/i })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('#lab-panel-batch .launch-view')).toBeVisible()
  // Back to scoring: keyboard on the tablist
  await page.getByRole('tab', { selected: true }).press('ArrowLeft')
  await expect(page).not.toHaveURL(/tab=batch/)
  // The tab stays mounted (hidden) so a running batch is not aborted
  await expect(page.locator('#lab-panel-batch')).toBeHidden()
  await expect(page.locator('#lab-panel-score')).toBeVisible()
  // No second entry point to /batch-run left in the Lab
  await expect(page.locator('a[href="/batch-run"]')).toHaveCount(0)
})

test('Batch tab shows an error with retry when its chunk fails to load', async ({ page, guard }) => {
  guard.allow(/BatchRunView|Failed to load resource/)
  let fail = true
  await page.route(/BatchRunView/, (route) => (fail ? route.abort() : route.continue()))
  await page.goto('/lab?tab=batch')
  const alert = page.locator('#lab-panel-batch [role="alert"]')
  await expect(alert).toBeVisible()
  fail = false
  await alert.getByRole('button').click()
  await expect(page.locator('#lab-panel-batch .launch-view')).toBeVisible()
})

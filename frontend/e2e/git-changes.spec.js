import { test, expect } from './helpers/fixture.js'
import { WORKFLOW_FILE, pickConnection } from './helpers/workflow.js'

// The Sản phẩm tab's "Thay đổi của lượt chạy" panel (git checkpoints). The git side is covered by backend tests
// on real temp repos; here the three endpoints are mocked so the UI states can be driven without tokens.
test.beforeEach(async ({ page, request }) => {
  test.skip(!(await pickConnection(request)), 'needs a signed-in CLI connection to open a session')
  await page.setViewportSize({ width: 1440, height: 900 })
})

const DIFF = '@@ -1 +1 @@\n-old line\n+new line\n'
const FILES = () => [
  { path: 'src/a.js', change: 'modified', state: 'pending', diff: DIFF, binary: false, truncated: false },
  { path: 'b.txt', change: 'added', state: 'pending', diff: '@@ -0,0 +1 @@\n+hello\n', binary: false, truncated: false },
]

async function openProducts(page) {
  await page.goto(`/launch?workflow=${WORKFLOW_FILE}`)
  await page.getByLabel('Nhập tin nhắn').fill('git changes e2e')
  await page.locator('.composer-send:not(.is-stop)').last().click()
  await expect(page.getByText('Chờ bạn duyệt: Approval').first()).toBeVisible({ timeout: 90_000 })
  await page.getByRole('tab', { name: /Sản phẩm/ }).click()
}

async function stopRun(page) {
  const stop = page.locator('.composer-send.is-stop')
  if (await stop.count()) await stop.click()
}

test('git changes: diff, confirm, undo with a per-file conflict message, keep as branch', async ({ page }) => {
  const calls = { undo: [], branch: 0 }
  let undone = false
  await page.route(/\/api\/sessions\/[^/]+\/outputs\/changes(\/.*)?$/, async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (request.method() === 'GET') {
      const files = FILES().map((f) => (undone && f.path === 'src/a.js' ? { ...f, state: 'reverted' } : f))
      if (undone) files[1].state = 'conflict'
      const counts = { pending: files.filter((f) => f.state === 'pending').length, reverted: undone ? 1 : 0, conflict: undone ? 1 : 0 }
      return route.fulfill({ json: { status: 'ok', turn: 2, files, total: files.length, truncated: false, counts } })
    }
    if (path.endsWith('/undo')) {
      calls.undo.push(request.postDataJSON())
      undone = true
      return route.fulfill({ json: { status: 'ok', turn: 2, restored: ['src/a.js'], removed: [], conflicts: [{ path: 'b.txt', reason: 'modified_after_run' }], errors: [] } })
    }
    calls.branch += 1
    return route.fulfill({ json: { status: 'ok', turn: 2, branch: 'agentdev/run-e2e', commit: 'abc' } })
  })
  await openProducts(page)

  const panel = page.getByTestId('git-changes')
  await expect(panel).toBeVisible()
  await expect(panel.getByRole('list', { name: 'Các file đã thay đổi' }).getByRole('listitem')).toHaveCount(2)
  await expect(panel.locator('.dl.t-add')).toContainText('new line')
  await expect(panel.locator('.dl.t-del')).toContainText('old line')
  await panel.getByRole('button', { name: /b\.txt/ }).click()
  await expect(panel.locator('.dl.t-add')).toContainText('hello')

  // Cancel keeps everything as it is
  await panel.getByTestId('git-undo').click()
  const dialog = page.getByRole('alertdialog')
  await expect(dialog).toContainText('Hoàn tác lượt này?')
  await dialog.getByRole('button', { name: 'Hủy' }).click()
  await expect(dialog).toHaveCount(0)
  expect(calls.undo).toHaveLength(0)

  await panel.getByTestId('git-undo').click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Hoàn tác' }).click()
  await expect(panel.getByTestId('git-notice')).toContainText('Đã khôi phục 1 file')
  await expect(panel.getByTestId('git-problems')).toContainText('b.txt: bạn đã sửa file này sau lượt chạy')
  expect(calls.undo).toEqual([{ paths: null }])
  await expect(panel.getByText('Đã hoàn tác')).toBeVisible()
  await expect(panel.getByTestId('git-undo')).toBeDisabled() // nothing pending any more

  await panel.getByTestId('git-keep-branch').click()
  await expect(panel.getByTestId('git-notice')).toContainText('agentdev/run-e2e')
  expect(calls.branch).toBe(1)
  await stopRun(page)
})

test('git changes: error state tells how to fix it and retry recovers', async ({ page, guard }) => {
  guard.allow(/outputs\/changes/)
  let failing = true
  await page.route(/\/api\/sessions\/[^/]+\/outputs\/changes$/, (route) => {
    if (failing) return route.fulfill({ status: 500, json: { detail: 'git exploded' } })
    return route.fulfill({ json: { status: 'ok', turn: 1, files: [], total: 0, truncated: false, counts: {} } })
  })
  await openProducts(page)
  const panel = page.getByTestId('git-changes')
  await expect(panel.getByTestId('git-error')).toContainText('Kiểm tra máy đã cài git')
  failing = false
  await panel.getByRole('button', { name: 'Thử lại' }).click()
  await expect(panel.getByTestId('git-empty')).toContainText('Lượt này không sửa file nào.')
  await stopRun(page)
})

test('git changes: a folder that is not a git repo says why there is no undo', async ({ page }) => {
  await page.route(/\/api\/sessions\/[^/]+\/outputs\/changes$/, (route) =>
    route.fulfill({ json: { status: 'not_git', files: [] } }))
  await openProducts(page)
  await expect(page.getByTestId('git-unavailable')).toContainText('không phải kho git')
  await stopRun(page)
})

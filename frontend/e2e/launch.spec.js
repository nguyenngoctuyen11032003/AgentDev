import { test, expect } from './helpers/fixture.js'
import { WORKFLOW_FILE, pickConnection } from './helpers/workflow.js'

// Fake literal workflow: the only agent step asks the signed-in CLI for a model that does not exist, so
// it is rejected before any tokens are used. No paid step is ever run here.
test.beforeEach(async ({ page, request }) => {
  test.skip(!(await pickConnection(request)), 'needs a signed-in CLI connection for the failing step')
  await page.setViewportSize({ width: 1440, height: 900 })
})

const composer = (page) => page.getByLabel('Nhập tin nhắn')
const send = (page) => page.locator('.composer-send:not(.is-stop)').last()

async function startRun(page, text = 'chạy thử e2e') {
  await page.goto(`/launch?workflow=${WORKFLOW_FILE}`)
  await composer(page).fill(text)
  await send(page).click()
  await expect(page.getByText('Approval đang hỏi bạn').first()).toBeVisible({ timeout: 90_000 })
}

test('launch: a fresh page shows the workflow and no run yet', async ({ page }) => {
  await page.goto(`/launch?workflow=${WORKFLOW_FILE}`)
  await expect(composer(page)).toBeVisible()
  await expect(page.locator('.chat-messages')).not.toContainText('E2E FINISHED')
  await expect(page.locator('.composer-send.is-stop')).toHaveCount(0)
  expect(new URL(page.url()).searchParams.get('session')).toBeNull()
})

test('launch: send stops at the approval gate; silence does not approve it; Stop cancels the run', async ({ page }) => {
  await startRun(page)
  // The run is paused on the gate and must not complete by itself.
  await page.waitForTimeout(3000)
  await expect(page.locator('.chat-header-status')).not.toContainText('Hoàn tất')
  await expect(page.locator('.chat-messages')).not.toContainText('E2E FINISHED')
  expect(new URL(page.url()).searchParams.get('session')).toBeTruthy()

  const stop = page.locator('.composer-send.is-stop')
  await expect(stop).toBeVisible()
  await stop.click()
  await expect(page.locator('.chat-header-status')).toContainText(/Đã hủy|Đã dừng/, { timeout: 30_000 })
  await expect(page.locator('.chat-messages')).not.toContainText('E2E FINISHED')
  await expect(page.locator('.composer-send.is-stop')).toHaveCount(0)
})

test('launch: reload restores the session and its messages, still not approved', async ({ page }) => {
  await startRun(page, 'phiên cần khôi phục e2e')
  const session = new URL(page.url()).searchParams.get('session')
  await page.reload()
  expect(new URL(page.url()).searchParams.get('session')).toBe(session)
  await expect(page.locator('.chat-messages')).toContainText('phiên cần khôi phục e2e')
  await expect(page.locator('.chat-messages')).not.toContainText('E2E FINISHED')
  // Leave nothing running: stop it if the gate is still active.
  const stop = page.locator('.composer-send.is-stop')
  if (await stop.count()) await stop.click()
})

test('launch: approving the gate through the composer finishes the run, then the Sản phẩm tab shows its state', async ({ page }) => {
  await startRun(page, 'phiên sản phẩm e2e')
  await composer(page).fill('OK')
  await page.locator('.composer-send').last().click()
  await expect(page.locator('.chat-header-status')).toContainText('Hoàn tất', { timeout: 60_000 })
  await expect(page.locator('.chat-messages')).toContainText('E2E FINISHED')

  await page.getByRole('tab', { name: /Sản phẩm/ }).click()
  await expect(page.getByRole('tab', { name: /Sản phẩm/ })).toHaveAttribute('aria-selected', 'true')
  // The fake workflow writes no files: an empty / missing-folder message, never a spinner that never ends.
  await expect(page.getByText(/Chưa có thư mục kết quả|Thư mục kết quả đang trống/).first()).toBeVisible({ timeout: 20_000 })
  await page.getByRole('tab', { name: /Tổng quan/ }).click()
  await expect(page.locator('.pipe-step').first()).toBeVisible()
})

test('launch: the session list keeps the run and can open it again', async ({ page }) => {
  await startRun(page, 'phiên trong danh sách e2e')
  const session = new URL(page.url()).searchParams.get('session')
  const stop = page.locator('.composer-send.is-stop')
  if (await stop.count()) await stop.click()
  await page.goto(`/launch?workflow=${WORKFLOW_FILE}`)
  const row = page.getByText('phiên trong danh sách e2e').first()
  const expand = page.getByRole('button', { name: 'Mở danh sách phiên' })
  if (await expand.isVisible()) await expand.click()
  await expect(row).toBeVisible({ timeout: 20_000 })
  await row.click()
  await expect(page).toHaveURL(new RegExp(`session=${session}`))
})

import { test, expect } from './helpers/fixture.js'
import { mockConnections } from './helpers/mocks.js'

test.beforeEach(async ({ page }) => { await page.setViewportSize({ width: 1440, height: 900 }) })

test('settings/connections: a signed-in account is listed with status, models and fallback info', async ({ page }) => {
  await mockConnections(page)
  await page.goto('/settings/connections')
  const card = page.locator('.connection-card', { hasText: 'Claude E2E' })
  await expect(card).toBeVisible()
  await expect(card.locator('.status-pill')).toContainText('Hoạt động')
  await expect(card.locator('.default-badge')).toBeVisible()
  await expect(page.locator('.provider-card')).toHaveCount(3)
  await expect(page.locator('.fallback-card')).toBeVisible()
})

test('settings/connections: test button reports success', async ({ page }) => {
  await mockConnections(page)
  await page.goto('/settings/connections')
  await page.locator('.connection-card').getByRole('button', { name: 'Kiểm tra' }).click()
  await expect(page.getByText(/Đã kết nối — có 1 model/)).toBeVisible()
})

test('settings/connections: logout asks for confirmation, Cancel keeps it, confirm removes it', async ({ page }) => {
  const state = await mockConnections(page)
  await page.goto('/settings/connections')
  const logout = page.getByRole('button', { name: 'Đăng xuất: Claude E2E' })
  await logout.click()
  const dialog = page.getByRole('alertdialog')
  await expect(dialog).toContainText('Đăng xuất "Claude E2E"?')
  await dialog.getByRole('button', { name: 'Hủy' }).click()
  await expect(dialog).toBeHidden()
  expect(state.deleted).toEqual([])

  await logout.click()
  await dialog.getByRole('button', { name: 'Đăng xuất' }).click()
  await expect(page.locator('.connection-card')).toHaveCount(0)
  await expect(page.locator('.empty-state')).toContainText('Chưa có kết nối nào')
  expect(state.deleted).toEqual(['e2e-claude'])
})

test('settings/connections: load error is shown to the user, page does not spin forever', async ({ page, guard }) => {
  guard.allow(/\/api\/connections|Failed to load resource/)
  await mockConnections(page, { failList: true })
  await page.goto('/settings/connections')
  await expect(page.getByText('Không thể tải danh sách kết nối').first()).toBeVisible()
  await expect(page.locator('.skeleton')).toHaveCount(0)
})

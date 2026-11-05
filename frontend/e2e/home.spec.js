import { test, expect } from './helpers/fixture.js'

test.beforeEach(async ({ page }) => { await page.setViewportSize({ width: 1440, height: 900 }) })

test('home: hero renders and "Bắt đầu" opens the tutorial', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('AgentDev')
  await page.getByRole('link', { name: /Bắt đầu/ }).first().click()
  await expect(page).toHaveURL(/\/tutorial$/)
  await expect(page.locator('.markdown-body')).toBeVisible()
})

test('home: secondary button opens the workflow list', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'Mở quy trình' }).click()
  await expect(page).toHaveURL(/\/workflows$/)
})

test('nav: every sidebar link reaches its page and highlights as active', async ({ page }) => {
  await page.goto('/')
  const nav = page.locator('.sidebar-nav')
  for (const [name, url] of [['Hướng dẫn', /\/tutorial$/], ['Quy trình', /\/workflows/], ['Phòng thí nghiệm', /\/lab$/], ['Trang chủ', /\/$/]]) {
    await nav.getByRole('link', { name, exact: true }).click()
    await expect(page).toHaveURL(url)
    await expect(nav.locator('a.router-link-active', { hasText: name })).toHaveCount(1)
  }
  // "Chạy" opens in a new tab (target=_blank)
  const popupPromise = page.context().waitForEvent('page')
  await nav.getByRole('link', { name: 'Chạy', exact: true }).click()
  const popup = await popupPromise
  await popup.waitForLoadState('domcontentloaded')
  expect(new URL(popup.url()).pathname).toBe('/launch')
  await popup.close()
  await page.getByRole('link', { name: 'Cài đặt', exact: true }).click()
  await expect(page).toHaveURL(/\/settings\/general$/)
})

test('nav: old /connections and /skills addresses redirect into settings', async ({ page }) => {
  await page.route('**/api/connections**', (r) => r.fulfill({ json: { connections: [] } }))
  await page.route('**/api/skills**', (r) => r.fulfill({ json: { skills: [] } }))
  await page.goto('/connections')
  await expect(page).toHaveURL(/\/settings\/connections/)
  await page.goto('/skills')
  await expect(page).toHaveURL(/\/settings\/skills/)
})

import { test, expect } from './helpers/fixture.js'

const KEY = 'agent_config_settings'
const stored = (page) => page.evaluate((k) => JSON.parse(localStorage.getItem(k) || '{}'), KEY)

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/settings/general')
  // Start every test from the defaults (each test gets a fresh browser context, so this is local to it).
  await page.evaluate((k) => localStorage.removeItem(k), KEY)
  await page.reload()
})

test('settings/general: theme choice applies, persists and survives reload', async ({ page }) => {
  await page.getByRole('radio', { name: /Sáng/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  expect((await stored(page)).THEME).toBe('light')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await expect(page.getByRole('radio', { name: /Sáng/ })).toHaveAttribute('aria-checked', 'true')
  await page.getByRole('radio', { name: /Tối/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
})

test('settings/general: "Hệ thống" follows the OS colour scheme', async ({ page }) => {
  await page.getByRole('radio', { name: /Hệ thống/ }).click()
  await page.emulateMedia({ colorScheme: 'light' })
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
})

test('settings/general: each behaviour switch flips, persists and survives reload', async ({ page }) => {
  const keys = { 'Bật chú thích trợ giúp': 'ENABLE_HELP_TOOLTIPS', 'Tự động hiện cài đặt nâng cao': 'AUTO_SHOW_ADVANCED' }
  const flipped = {}
  for (const [label, key] of Object.entries(keys)) {
    const sw = page.getByRole('switch', { name: label })
    const before = (await sw.getAttribute('aria-checked')) === 'true'
    await sw.click()
    await expect(sw).toHaveAttribute('aria-checked', String(!before))
    await expect.poll(async () => (await stored(page))[key]).toBe(!before)
    flipped[label] = !before
  }
  await page.reload()
  for (const label of Object.keys(keys)) {
    await expect(page.getByRole('switch', { name: label })).toHaveAttribute('aria-checked', String(flipped[label]))
  }
})

test('settings/general: language switch changes the UI text and persists', async ({ page }) => {
  await page.locator('#gs-language').selectOption('en')
  await expect(page.getByRole('radio', { name: /Light/ })).toBeVisible()
  expect((await stored(page)).LANGUAGE).toBe('en')
  await page.reload()
  await expect(page.getByRole('radio', { name: /Light/ })).toBeVisible()
  await page.locator('#gs-language').selectOption('zh')
  await expect(page.getByRole('radio', { name: /Light/ })).toHaveCount(0)
  await expect(page.getByRole('radio', { name: /Sáng/ })).toHaveCount(0)
  await page.locator('#gs-language').selectOption('vi')
  await expect(page.getByRole('radio', { name: /Sáng/ })).toBeVisible()
})

test('settings: side navigation switches between the three pages', async ({ page }) => {
  await page.route('**/api/connections**', (r) => r.fulfill({ json: { connections: [], vendors: [] } }))
  await page.route('**/api/skills**', (r) => r.fulfill({ json: { skills: [] } }))
  const nav = page.locator('aside.settings-nav')
  await nav.getByRole('link', { name: /Kết nối/ }).click()
  await expect(page).toHaveURL(/settings\/connections/)
  await nav.getByRole('link', { name: /Skill/ }).click()
  await expect(page).toHaveURL(/settings\/skills/)
  await nav.getByRole('link', { name: /Chung/ }).click()
  await expect(page).toHaveURL(/settings\/general/)
})

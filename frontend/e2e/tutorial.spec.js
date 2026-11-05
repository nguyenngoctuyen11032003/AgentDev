import { test, expect } from './helpers/fixture.js'

test.beforeEach(async ({ page }) => { await page.setViewportSize({ width: 1440, height: 900 }) })

test('tutorial: TOC lists headings and a click jumps to the anchor', async ({ page }) => {
  await page.goto('/tutorial')
  const toc = page.locator('nav.toc')
  await expect(toc).toBeVisible()
  const links = toc.locator('a')
  expect(await links.count()).toBeGreaterThan(3)
  const target = links.nth(3)
  const id = (await target.getAttribute('href')).slice(1)
  await target.click()
  await expect(page).toHaveURL(new RegExp(`#${id}$`))
  await expect(page.locator(`[id="${id}"]`)).toBeInViewport()
  await expect(target).toHaveAttribute('aria-current', 'location')
})

test('tutorial: a deep link #hash scrolls to its heading', async ({ page }) => {
  await page.goto('/tutorial')
  const id = (await page.locator('nav.toc a').nth(4).getAttribute('href')).slice(1)
  await page.goto(`/tutorial#${id}`)
  await expect(page.locator(`[id="${id}"]`)).toBeInViewport()
})

test('tutorial: the article follows the saved language (vi, en, zh)', async ({ page }) => {
  const seen = {}
  for (const code of ['vi', 'en', 'zh']) {
    await page.addInitScript((c) => {
      const k = 'agent_config_settings'
      localStorage.setItem(k, JSON.stringify({ ...JSON.parse(localStorage.getItem(k) || '{}'), LANGUAGE: c }))
    }, code)
    await page.goto('/tutorial')
    await expect(page.locator('.markdown-body h1').first()).toBeVisible()
    seen[code] = await page.locator('.markdown-body h1').first().innerText()
  }
  expect(new Set(Object.values(seen)).size, `titles per language: ${JSON.stringify(seen)}`).toBe(3)
})

test('tutorial: load error shows a message with retry, retry recovers', async ({ page, guard }) => {
  guard.allow(/tutorial-vi\.md|Không thể tải nội dung hướng dẫn/)
  let fail = true
  await page.route('**/tutorial-vi.md', (r) => (fail ? r.fulfill({ status: 500, body: 'boom' }) : r.continue()))
  await page.goto('/tutorial')
  await expect(page.getByRole('alert')).toContainText('Không tải được hướng dẫn')
  fail = false
  await page.getByRole('button', { name: 'Thử lại' }).click()
  await expect(page.locator('.markdown-body')).toBeVisible()
  await expect(page.locator('nav.toc')).toBeVisible()
})

import { test, expect } from '@playwright/test'
import { WORKFLOW_ID } from './helpers/workflow.js'

test('settings dialog: focus starts inside, Tab never leaves, Esc closes and returns focus', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/launch')
  const trigger = page.locator('.settings-button')
  await trigger.click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  await expect.poll(() => dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true)
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press(i % 7 === 6 ? 'Shift+Tab' : 'Tab')
    expect(await dialog.evaluate((el) => el.contains(document.activeElement)), `Tab #${i + 1} left the dialog`).toBe(true)
  }
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(trigger).toBeFocused()
})

test('workflow canvas controls are named and at least 24x24', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(`/workflows/${WORKFLOW_ID}`)
  await page.waitForSelector('.vue-flow__node')
  const buttons = page.locator('.vue-flow__controls-button')
  await expect(buttons).toHaveCount(4)
  for (let i = 0; i < 4; i++) {
    const b = buttons.nth(i)
    await expect(b).toHaveAttribute('aria-label', /\S/)
    await expect(b).toHaveAttribute('title', /\S/)
    const box = await b.boundingBox()
    expect(box.width).toBeGreaterThanOrEqual(24)
    expect(box.height).toBeGreaterThanOrEqual(24)
  }
  const first = await buttons.first().getAttribute('aria-label')
  await buttons.nth(3).click()
  await expect(buttons.nth(3)).toHaveAttribute('aria-label', /Mở khóa/)
  expect(first).toBe('Phóng to')
})

test('workflow canvas controls keep their names after graph -> YAML -> graph', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(`/workflows/${WORKFLOW_ID}`)
  await page.waitForSelector('.vue-flow__node')
  await page.locator('.tab-buttons .tab').nth(1).click()
  await expect(page.locator('.yaml-editor')).toBeVisible()
  await page.locator('.tab-buttons .tab').nth(0).click()
  await page.waitForSelector('.vue-flow__node')
  const buttons = page.locator('.vue-flow__controls-button')
  await expect(buttons).toHaveCount(4)
  for (let i = 0; i < 4; i++) {
    await expect(buttons.nth(i)).toHaveAttribute('aria-label', /\S/)
    await expect(buttons.nth(i)).toHaveAttribute('title', /\S/)
  }
  await expect(buttons.first()).toHaveAttribute('aria-label', 'Phóng to')
})

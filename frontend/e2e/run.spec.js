/* global process */
import fs from 'node:fs'
import { test, expect } from '@playwright/test'
import { WORKFLOW_FILE, pickConnection } from './helpers/workflow.js'
import { measureHeap } from './helpers/heap.js'

const step = (page, name) => page.locator('.pipe-step').filter({ has: page.locator('.pipe-name', { hasText: new RegExp(`^${name}$`) }) })

test('run fake workflow: approve the gate, soft-failing step is shown as failed, run completes', async ({ page, request }) => {
  test.skip(!(await pickConnection(request)), 'needs a signed-in CLI connection for the failing step')
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(`/launch?workflow=${WORKFLOW_FILE}`)

  const input = page.getByLabel('Nhập tin nhắn')
  await input.fill('chạy thử e2e')
  await page.locator('.composer-send').click()

  // The gate asks the person; the run is paused there.
  await expect(page.getByText('Approval đang hỏi bạn').first()).toBeVisible({ timeout: 90_000 })
  await expect(page.locator('.chat-header-status')).not.toContainText('Hoàn tất')
  expect(new URL(page.url()).searchParams.get('session')).toBeTruthy()

  await input.fill('OK')
  await page.locator('.composer-send').click()
  await expect(page.locator('.chat-header-status')).toContainText('Hoàn tất', { timeout: 60_000 })
  await expect(page.locator('.chat-messages')).toContainText('E2E FINISHED')

  // The engine warns that the optional step failed but the run goes on.
  await expect(page.locator('.chat-messages')).toContainText('continue_on_error is set')

  await page.locator('.view-tab').filter({ hasText: 'Tổng quan' }).first().click()
  await expect(step(page, 'Branch Soft')).toHaveClass(/is-error/)
  for (const name of ['Plan', 'Branch Ok', 'Merge', 'Approval', 'Final']) {
    await expect(step(page, name), `${name} should be done`).toHaveClass(/is-done/)
  }
  fs.mkdirSync('e2e/artifacts/round2', { recursive: true })
  await page.screenshot({ path: `e2e/artifacts/round2/${process.env.E2E_SHOT || 'after'}.png` })

  // One of 6 steps was skipped on error: progress must say 5/6 (83%), never a forced 100%,
  // and the status must admit the failed step instead of a plain "Hoàn thành".
  const meter = page.locator('.hero-progress').first()
  await expect(meter).toContainText('5/6')
  await expect(meter).toContainText('83%')
  await expect(meter).not.toContainText('100%')
  await expect(page.getByText('Hoàn thành, 1 bước lỗi').locator('visible=true').first()).toBeVisible()

  const heap = await measureHeap(page)
  console.log(`[e2e] JS heap after run: ${heap.usedMB} MB used / ${heap.totalMB} MB total`)
  expect(errors).toEqual([])
})

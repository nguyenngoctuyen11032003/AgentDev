import { test, expect } from './helpers/fixture.js'
import { WORKFLOW_FILE, pickConnection } from './helpers/workflow.js'

// "Prompt cho Flow": a production package in the Sản phẩm tab shows per-shot prompts to paste into Google Flow.
// The session's file listing is mocked; the prompts come from the real backend (/api/video/flow-prompts, no model).
test.beforeEach(async ({ page, request }) => {
  test.skip(!(await pickConnection(request)), 'needs a signed-in CLI connection to open a session')
  await page.setViewportSize({ width: 1440, height: 900 })
})

const PACKAGE = `# GÓI SẢN XUẤT - Tập 1
Tổng: 2 cảnh quay. Style chung: photorealistic, 9:16 vertical

| # | Giây | Thời lượng | Khung hình |
|---|------|-----------|-----------|
| 1 | 0-5 | 5 | ECU |
| 2 | 5-11 | 6 | MS |

**1.** IMG: Close-up of [LINH-v1] waking up. VID: Handheld jolt.

**2.** IMG: [LINH-v1] meets [AN-v1] in a dark room. VID: Slow push-in.
`
const BIBLE = `# Hồ sơ
## LINH [LINH-v1]
- Appearance: Vietnamese woman, 28, grey hoodie.
`
const FILES = {
  'series/tap_1/goi_san_xuat.md': PACKAGE,
  'series/ho_so_nhan_vat.md': BIBLE,
}

async function mockSessionFiles(page) {
  await page.route(/\/api\/sessions\/[^/]+\/outputs\/files$/, (route) => route.fulfill({
    json: {
      available: true, root: 'D:/AgentDev/e2e', truncated: false, project: null, location: 'session',
      file_count: 2, total_bytes: PACKAGE.length + BIBLE.length,
      files: Object.entries(FILES).map(([path, text]) => ({ path, size: text.length, kind: 'markdown' })),
    },
  }))
  await page.route(/\/api\/sessions\/[^/]+\/outputs\/file\?/, (route) => {
    const path = new URL(route.request().url()).searchParams.get('path')
    return route.fulfill({ body: FILES[path], contentType: 'text/markdown; charset=utf-8' })
  })
}

test('production package: per-shot prompts for Google Flow, with tags expanded and copy', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await mockSessionFiles(page)
  await page.goto(`/launch?workflow=${WORKFLOW_FILE}`)
  await page.getByLabel('Nhập tin nhắn').fill('flow prompts e2e')
  await page.locator('.composer-send:not(.is-stop)').last().click()
  await expect(page.getByText('Chờ bạn duyệt: Approval').first()).toBeVisible({ timeout: 90_000 })
  await page.getByRole('tab', { name: /Sản phẩm/ }).click()

  await page.getByRole('button', { name: /goi_san_xuat\.md/ }).click()
  await page.getByRole('button', { name: 'Prompt cho Flow' }).click()

  const shots = page.locator('.fl-shot')
  await expect(shots).toHaveCount(2)
  await expect(shots.first()).toContainText('Cảnh 1')
  await expect(shots.first()).toContainText('5 giây')
  await expect(shots.nth(1)).toContainText('(Vietnamese woman, 28, grey hoodie) meets [AN-v1] in a dark room. Motion: Slow push-in.')
  await expect(page.getByRole('note')).toContainText('AN-v1') // no appearance for this tag

  await shots.nth(1).getByRole('button', { name: 'Chép prompt video' }).click()
  await expect(shots.nth(1).getByRole('button', { name: 'Đã chép' })).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('Motion: Slow push-in.')

  // Back to the rendered package
  await page.getByRole('button', { name: 'Trình bày' }).click()
  await expect(shots).toHaveCount(0)
  const stop = page.locator('.composer-send.is-stop')
  if (await stop.count()) await stop.click()
})

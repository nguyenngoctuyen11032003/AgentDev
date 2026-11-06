import { test, expect } from './helpers/fixture.js'
import { mockSkills } from './helpers/mocks.js'

const NAME = 'zz-e2e-skill'
const BODY = `---\nname: ${NAME}\ndescription: Dung khi chay e2e\n---\n# E2E\nNoi dung.`

test.beforeEach(async ({ page }) => { await page.setViewportSize({ width: 1440, height: 900 }) })

test('settings/skills: empty library shows the empty state with both actions', async ({ page }) => {
  await mockSkills(page, [])
  await page.goto('/settings/skills')
  await expect(page.locator('.empty-state')).toContainText('Chưa có skill nào')
  await expect(page.locator('.empty-state').getByRole('button', { name: 'Thêm skill' })).toBeVisible()
})

test('settings/skills: add, edit, search and delete a skill (in-memory mock, library untouched)', async ({ page }) => {
  const state = await mockSkills(page, [{ name: 'existing-one', description: 'Da co san' }])
  await page.goto('/settings/skills')
  await expect(page.locator('.skill-card')).toHaveCount(1)

  // add: pasting frontmatter fills the name and description fields
  await page.getByRole('button', { name: 'Thêm skill' }).first().click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox', { name: 'Nội dung' }).fill(BODY)
  await dialog.getByRole('textbox', { name: 'Nội dung' }).press('End')
  await dialog.getByPlaceholder('cto-management').fill(NAME)
  await dialog.getByPlaceholder(/Dùng khi lập kế hoạch/).fill('Dung khi chay e2e')
  await dialog.getByRole('button', { name: 'Lưu skill' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.locator('.skill-card', { hasText: NAME })).toBeVisible()
  await expect(page.locator('.count')).toContainText('2 skill')

  // edit the description
  await page.getByRole('button', { name: `Sửa: ${NAME}` }).click()
  await expect(dialog.getByPlaceholder('cto-management')).toHaveValue(NAME)
  await dialog.getByPlaceholder(/Dùng khi lập kế hoạch/).fill('Mo ta moi')
  await dialog.getByRole('button', { name: 'Lưu skill' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.locator('.skill-card', { hasText: NAME })).toContainText('Mo ta moi')
  expect(state.calls).toContain(`PUT /${NAME}`)

  // search narrows the grid, no match shows a message
  await page.getByRole('searchbox').fill('zz-e2e')
  await expect(page.locator('.skill-card')).toHaveCount(1)
  await page.getByRole('searchbox').fill('khong-co-skill-nay')
  await expect(page.locator('.no-match')).toBeVisible()
  await page.getByRole('searchbox').fill('')

  // delete: confirm dialog, then the card is gone
  await page.getByRole('button', { name: `Xóa: ${NAME}` }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Xóa' }).click()
  await expect(page.locator('.skill-card', { hasText: NAME })).toHaveCount(0)
  expect(state.skills.map((s) => s.name)).toEqual(['existing-one'])
})

test('settings/skills: saving an existing name asks before overwriting', async ({ page, guard }) => {
  // BUG P0-E2E-01 (docs/audit/findings/phase0-e2e.md): the overwrite confirm opens under the edit dialog, so its buttons cannot be clicked.
  test.fixme(true, 'P0-E2E-01: confirm dialog is covered by the skill editor backdrop (same z-index, earlier in DOM)')
  guard.allow(/api\/skills/)
  const state = await mockSkills(page, [{ name: NAME, description: 'old' }])
  await page.goto('/settings/skills')
  await page.getByRole('button', { name: 'Thêm skill' }).first().click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox', { name: 'Nội dung' }).fill(BODY)
  await dialog.getByPlaceholder('cto-management').fill(NAME)
  await dialog.getByRole('button', { name: 'Lưu skill' }).click()
  await expect(page.getByRole('alertdialog')).toContainText('Skill đã tồn tại')
  await page.getByRole('alertdialog').getByRole('button', { name: 'Ghi đè' }).click()
  await expect(dialog).toBeHidden()
  expect(state.skills).toHaveLength(1)
})

test('settings/skills: load error shows a toast and the page leaves the loading state', async ({ page, guard }) => {
  guard.allow(/\/api\/skills|Failed to load resource/)
  await page.route('**/api/skills**', (r) => r.fulfill({ status: 500, json: { detail: 'boom' } }))
  await page.goto('/settings/skills')
  await expect(page.locator('.skeleton')).toHaveCount(0)
  await expect(page.locator('.toast, [role="alert"], [role="status"]').filter({ hasText: /skill|boom/i }).first()).toBeVisible()
})

test('settings/skills: categories group the library, filter it and set a skill category', async ({ page }) => {
  const state = await mockSkills(page, [
    { name: 'remotion-render', description: 'Render MP4', category: 'video', category_source: 'auto' },
    { name: 'heygen-avatar', description: 'Avatar video', category: 'video', category_source: 'auto' },
    { name: 'kling-prompting', description: 'Prompt Kling', category: 'video', category_source: 'auto' },
    { name: 'ffmpeg', description: 'Cut clips', category: 'video', category_source: 'auto' },
    { name: 'moviepy', description: 'Edit in Python', category: 'video', category_source: 'auto' },
    { name: 'systematic-debugging', description: 'When a test fails', category: 'dev', category_source: 'auto' }
  ])
  await page.goto('/settings/skills')

  // "All": one section per category, long ones show a preview and a "see all" button
  await expect(page.getByRole('heading', { name: /Video/ })).toBeVisible()
  await expect(page.getByRole('heading', { name: /Lập trình/ })).toBeVisible()
  await expect(page.locator('.skill-card')).toHaveCount(5) // 4 video (preview) + 1 dev
  await page.getByRole('button', { name: 'Xem cả 5' }).click()

  // one category: every skill in it, remembered in the URL
  await expect(page).toHaveURL(/cat=video/)
  await expect(page.getByRole('button', { name: /Video/, pressed: true })).toBeVisible()
  await expect(page.locator('.skill-card')).toHaveCount(5)
  await expect(page.locator('.skill-card', { hasText: 'systematic-debugging' })).toHaveCount(0)

  // the editor shows the guessed category and sends a new one only when changed
  await page.getByRole('button', { name: 'Sửa: ffmpeg' }).click()
  const dialog = page.getByRole('dialog')
  const select = dialog.getByRole('combobox', { name: 'Loại' })
  await expect(select.locator('option:checked')).toHaveText('Tự động (Video)')
  await select.selectOption('dev')
  const put = page.waitForRequest((r) => r.method() === 'PUT')
  await dialog.getByRole('button', { name: 'Lưu skill' }).click()
  expect((await put).postDataJSON().category).toBe('dev')
  expect(state.calls).toContain('PUT /ffmpeg')

  // back to every category
  await page.getByRole('button', { name: /Tất cả/ }).click()
  await expect(page).not.toHaveURL(/cat=/)
})

test('settings/skills: a card shows the plain-language guide and opens a detail view', async ({ page }) => {
  const guide = { purpose: 'Tạo video người dẫn chuyện', when: 'cần video có người nói', benefit: 'Video tự nhiên', requires: 'API key HeyGen', paid: true }
  await mockSkills(page, [{ name: 'heygen-video', description: 'Presenter videos', category: 'video', category_source: 'manual', guide }])
  await page.goto('/settings/skills')
  const card = page.locator('.skill-card', { hasText: 'heygen-video' })
  await expect(card).toContainText('Tạo video người dẫn chuyện')
  await expect(card).toContainText('Trả phí')

  // Vietnamese words find the skill
  await page.getByRole('searchbox').fill('người dẫn')
  await expect(page.locator('.skill-card')).toHaveCount(1)

  await card.click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('Dùng để')
  await expect(dialog).toContainText('API key HeyGen')
  await expect(dialog).toContainText('Presenter videos')
  await dialog.getByRole('button', { name: 'Sửa' }).click()
  await expect(page.getByRole('dialog').getByPlaceholder(/Node.js, ffmpeg/)).toHaveValue('API key HeyGen')
})

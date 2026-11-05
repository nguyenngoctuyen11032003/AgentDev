import { test, expect } from './helpers/fixture.js'
import { API, buildYaml, pickConnection, WORKFLOW_ID } from './helpers/workflow.js'

// The editor tests get their own copy so editing never disturbs the fake workflow the run tests use.
const EDIT_ID = `${WORKFLOW_ID}_edit`
const EDIT_FILE = `${EDIT_ID}.yaml`
const node = (page, name) => page.locator('.vue-flow__node').filter({ hasText: name }).first()

test.describe.configure({ mode: 'serial' })

test.beforeEach(async ({ page, request }) => {
  const picked = (await pickConnection(request)) || { connection: 'none', provider: 'anthropic' }
  await request.delete(`${API}/api/workflows/${EDIT_FILE}/delete`).catch(() => {})
  const content = buildYaml(picked).replaceAll(WORKFLOW_ID, EDIT_ID)
  const res = await request.post(`${API}/api/workflows/upload/content`, { data: { filename: EDIT_FILE, content } })
  expect(res.ok(), await res.text()).toBe(true)
  await page.setViewportSize({ width: 1440, height: 900 })
})

test.afterEach(async ({ request }) => {
  await request.delete(`${API}/api/workflows/${EDIT_FILE}/delete`).catch(() => {})
})

const yamlOf = async (request) => (await (await request.get(`${API}/api/workflows/${EDIT_FILE}/get`)).json()).content

test('workflow: the graph shows every node and edge of the YAML', async ({ page }) => {
  await page.goto(`/workflows/${EDIT_ID}`)
  await expect(page.locator('.vue-flow__node')).toHaveCount(7) // 6 nodes + start marker
  await expect(page.locator('.vue-flow__edge')).toHaveCount(7)
  await expect(page.locator('.workflow-name')).toContainText(EDIT_ID)
})

test('workflow: edit a node, save, and the change reaches the YAML tab, the file and survives reload', async ({ page, request }) => {
  await page.goto(`/workflows/${EDIT_ID}`)
  await node(page, 'Plan').click()
  const desc = page.locator('#modal-0-description')
  await expect(desc).toBeVisible()
  await desc.fill('Mo ta sua boi e2e')
  await page.getByRole('button', { name: 'Lưu thay đổi' }).click()
  await expect(desc).toBeHidden()

  await page.getByRole('button', { name: 'Mã YAML' }).click()
  await expect(page.locator('.yaml-textarea')).toHaveValue(/Mo ta sua boi e2e/)
  await expect.poll(async () => await yamlOf(request)).toContain('Mo ta sua boi e2e')

  await page.reload()
  await node(page, 'Plan').click()
  await expect(page.locator('#modal-0-description')).toHaveValue('Mo ta sua boi e2e')
})

test('workflow: create an edge, it appears on the canvas and in the file', async ({ page, request }) => {
  await page.goto(`/workflows/${EDIT_ID}`)
  await expect(page.locator('.vue-flow__edge')).toHaveCount(7)
  await page.getByRole('button', { name: 'Tạo liên kết', exact: true }).click()
  const host = page.locator('.form-generator-host')
  await host.locator('#modal-0-from').fill('Plan')
  await host.locator('#modal-0-to').fill('Final')
  await host.getByRole('button', { name: 'Tạo liên kết' }).last().click()
  await expect(host).toBeHidden()
  await expect(page.locator('.vue-flow__edge')).toHaveCount(8)
  await expect.poll(async () => /from: Plan\s+to: Final/.test(await yamlOf(request))).toBe(true)
})

test('workflow: editing an edge opens its form with the current ends', async ({ page }) => {
  await page.goto(`/workflows/${EDIT_ID}`)
  await expect(page.locator('.vue-flow__edge')).toHaveCount(7)
  // Click the middle of the edge Merge -> Approval (its label/path box).
  const edge = page.locator('.vue-flow__edge[data-id*="Merge"][data-id*="Approval"]').first()
  await edge.locator('path').first().click({ force: true })
  const host = page.locator('.form-generator-host')
  await expect(host).toBeVisible()
  await expect(host.locator('#modal-0-from')).toHaveValue('Merge')
  await expect(host.locator('#modal-0-to')).toHaveValue('Approval')
})

test('workflow: the assistant panel opens, shows its context and closes without sending anything', async ({ page }) => {
  let sent = 0
  await page.route('**/api/workflow-assistant**', (route) => { if (route.request().method() === 'POST') sent += 1; return route.continue() })
  await page.goto(`/workflows/${EDIT_ID}`)
  await page.getByRole('button', { name: 'Mở trợ lý quy trình' }).click()
  const panel = page.getByRole('complementary', { name: /Trợ lý/ })
  await expect(panel).toBeVisible()
  await expect(panel.locator('.panel-context')).toBeVisible()
  await expect(panel.locator('textarea').first()).toBeVisible()
  await panel.getByRole('button', { name: /Đóng/ }).first().click()
  await expect(panel).toBeHidden()
  expect(sent).toBe(0) // no model call: it would spend tokens
})

test('workflow: the YAML tab shows the file read-only, so it cannot be broken by typing', async ({ page }) => {
  await page.goto(`/workflows/${EDIT_ID}`)
  await page.getByRole('button', { name: 'Mã YAML' }).click()
  const area = page.locator('.yaml-textarea')
  await expect(area).toHaveValue(/graph:/)
  await expect(area).toHaveAttribute('readonly', '')
  await expect(page.locator('.yaml-error')).toHaveCount(0)
  await page.getByRole('button', { name: 'Sơ đồ quy trình' }).click()
  await expect(page.locator('.vue-flow__node').first()).toBeVisible()
})

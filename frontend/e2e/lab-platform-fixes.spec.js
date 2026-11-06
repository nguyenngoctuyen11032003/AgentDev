/* global process */
// Lab "open platform fixes": list, verify polling, merge / discard dialogs (checkbox + password), and an
// axe WCAG A/AA scan of the section and dialogs at 375 + 1440, light + dark. Every /api/lab/platform-fixes
// route is mocked: nothing verifies, commits, merges or deletes a real branch.
import path from 'node:path'
import AxeBuilder from '@axe-core/playwright'
import { test, expect } from './helpers/fixture.js'
import { mockPlatformFixes, pickWorkflow } from './helpers/lab.js'

const SHOTS = process.env.E2E_SHOTS || ''
const GATES = ['forbidden_untouched', 'backend_sync', 'backend_tests', 'frontend_install', 'frontend_tests', 'frontend_lint', 'frontend_build', 'frontend_i18n']
const gates = (status, overrides = {}) =>
  GATES.map((code) => ({ code, status, summary: '', tail: '', command: `run ${code}`, ...(overrides[code] || {}) }))
const verifyOf = (status, gateList) => ({
  status,
  fingerprint: 'fp1',
  started_at: '2026-11-06T09:00:00Z',
  finished_at: status === 'running' ? null : '2026-11-06T09:05:00Z',
  frontend_changed: true,
  gates: gateList
})

const OK = {
  id: 'e2efix0001',
  branch: 'platform-fix/e2efix0001',
  worktree: 'D:/Code/Tuyen/agentdev-platform-fix-worktrees/e2efix0001-a-very-long-folder-name-for-wrapping',
  head: '0123456789abcdef0123',
  base: 'main',
  ahead: 2,
  dirty_files: 3,
  changed_files: ['backend/agentdev/runtime/node/executor/agent_executor.py', 'backend/tests/test_agent_executor.py', 'frontend/src/views/LabView.vue'],
  frontend_changed: true,
  forbidden_touched: [],
  verify: verifyOf('passed', gates('passed', { backend_tests: { summary: '812 passed in 95s', tail: '812 passed in 95.1s' } })),
  mergeable: true,
  blockers: []
}
const BLOCKED = {
  id: 'e2efix0002',
  branch: 'platform-fix/e2efix0002',
  worktree: 'D:/Code/Tuyen/agentdev-platform-fix-worktrees/e2efix0002',
  head: 'fedcba9876543210fedc',
  base: 'main',
  ahead: 1,
  dirty_files: 0,
  changed_files: ['backend/agentdev/api/routes/lab.py', 'backend/agentdev/runtime/graph.py'],
  frontend_changed: false,
  forbidden_touched: ['backend/agentdev/api/routes/lab.py'],
  verify: verifyOf(
    'failed',
    gates('passed', {
      forbidden_untouched: { status: 'failed', summary: '1 forbidden file changed' },
      backend_tests: { status: 'failed', summary: '2 failed, 810 passed', tail: 'FAILED tests/test_graph.py::test_loop - AssertionError\nFAILED tests/test_graph.py::test_end' },
      frontend_install: { status: 'skipped', summary: 'frontend/ not changed' }
    })
  ),
  mergeable: false,
  blockers: ['verify_required', 'forbidden_touched', 'ai_attribution']
}
const REPORT = '# Bản sửa e2efix0001\n\n- Đã làm: sửa vòng lặp\n- Còn lỗi: không\n<b>not html</b>'

const MERGE_RESULT = {
  commit: 'aaaaaaaaaa1111111111',
  merge_commit: 'bbbbbbbbbb2222222222',
  files: OK.changed_files,
  actions: [
    { code: 'committed', params: { commit: 'aaaaaaaaaa1111111111', branch: OK.branch, subject: 'fix(engine): stop the loop' } },
    { code: 'merged', params: { branch: OK.branch, into: 'main', commit: 'bbbbbbbbbb2222222222' } },
    { code: 'removed_worktree', params: { path: OK.worktree } },
    { code: 'deleted_branch', params: { branch: OK.branch } }
  ],
  next_steps: [{ code: 'restart_server', params: {} }, { code: 'push_when_ready', params: { branch: 'main' } }]
}
const DISCARD_RESULT = {
  actions: [
    { code: 'removed_worktree', params: { path: BLOCKED.worktree } },
    { code: 'deleted_branch', params: { branch: BLOCKED.branch } }
  ]
}

const err = (status, code, params = {}) => ({ status, json: { detail: { message: code, code, params } } })

/** Stateful mock of every platform-fix endpoint; `calls` records what the page sent. */
async function mockFixes(page, { items = [OK, BLOCKED], listFails = 0, mergeRefusal = null } = {}) {
  const state = { items: items.map((i) => ({ ...i })), polls: 0, listFails }
  const calls = { verify: [], cancel: [], merge: [], discard: [], list: 0 }
  await mockPlatformFixes(page, (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const rest = url.pathname.replace(/^.*\/api\/lab\/platform-fixes/, '')
    const [, id, action] = rest.split('/')
    const method = req.method()
    if (!id) {
      calls.list += 1
      if (state.listFails > 0) {
        state.listFails -= 1
        return route.fulfill({ status: 500, json: { detail: 'boom' } })
      }
      return route.fulfill({ json: { items: state.items } })
    }
    const index = state.items.findIndex((i) => i.id === id)
    if (index === -1) return route.fulfill(err(404, 'not_found'))
    const item = state.items[index]
    if (method === 'GET' && !action) {
      if (item.verify?.status === 'running') {
        state.polls += 1
        if (state.polls >= 2) {
          state.items[index] = { ...item, verify: verifyOf('passed', gates('passed')), mergeable: true, blockers: [], forbidden_touched: [] }
        } else {
          state.items[index] = { ...item, verify: verifyOf('running', gates('passed', { backend_tests: { status: 'running' }, frontend_build: { status: 'pending' } })) }
        }
      }
      return route.fulfill({ json: { ...state.items[index], report: REPORT } })
    }
    const body = req.postDataJSON() || {}
    if (action === 'verify') {
      calls.verify.push(id)
      state.polls = 0
      state.items[index] = { ...item, verify: verifyOf('running', gates('pending')) }
      return route.fulfill({ status: 202, json: { verify: state.items[index].verify } })
    }
    if (action === 'cancel') {
      calls.cancel.push(id)
      state.items[index] = { ...item, verify: verifyOf('cancelled', gates('cancelled')) }
      return route.fulfill({ json: { verify: state.items[index].verify } })
    }
    if (action === 'merge' || action === 'discard') {
      calls[action].push(body)
      if (body.password === 'wrong') return route.fulfill(err(403, 'bad_password', { attempts_left: 4 }))
      if (action === 'merge' && mergeRefusal) return route.fulfill(mergeRefusal)
      state.items.splice(index, 1)
      return route.fulfill({ json: action === 'merge' ? MERGE_RESULT : DISCARD_RESULT })
    }
    return route.fulfill(err(404, 'not_found'))
  })
  return calls
}

const section = (page) => page.locator('.pfs')
const itemOf = (page, item) => page.locator('.pfi').filter({ hasText: item.branch })
const MERGE = 'Commit + merge vào main + dọn nhánh'

async function openMerge(page) {
  await itemOf(page, OK).getByRole('button', { name: MERGE }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  return dialog
}

test.describe('lab platform fixes', () => {
  test.beforeEach(async ({ page }) => { await page.setViewportSize({ width: 1440, height: 900 }) })

  test('lists fixes with gates, forbidden files, blockers and the report as plain text', async ({ page }) => {
    await mockFixes(page)
    await pickWorkflow(page)
    await expect(section(page)).toBeVisible()
    await expect(section(page).locator('.pfi')).toHaveCount(2)

    const ok = itemOf(page, OK)
    await expect(ok).toContainText('HEAD 0123456789')
    await expect(ok).toContainText('Kiểm tra đạt')
    await expect(ok).toContainText('Sẵn sàng merge')
    await expect(ok.getByRole('button', { name: MERGE })).toBeEnabled()
    await ok.getByText('3 tệp đã đổi').click()
    await expect(ok.locator('.pfi-files')).toContainText('frontend/src/views/LabView.vue')
    await ok.getByText('Báo cáo ngắn').click()
    await expect(ok.getByLabel('Báo cáo ngắn')).toContainText('<b>not html</b>')
    await expect(ok.locator('.pfi-pre b')).toHaveCount(0)

    const blocked = itemOf(page, BLOCKED)
    await expect(blocked.getByRole('button', { name: MERGE })).toBeDisabled()
    await expect(blocked.locator('.pfi-forbidden')).toContainText('backend/agentdev/api/routes/lab.py')
    await expect(blocked).toContainText('Kiểm tra có bước lỗi')
    await expect(blocked).toContainText('2 failed, 810 passed')
    await blocked.locator('.pfi-tail summary').first().click()
    await expect(blocked.locator('.pfi-tail .pfi-pre').first()).toContainText('FAILED tests/test_graph.py::test_loop')
    const blockers = blocked.locator('.pfi-blockers')
    await expect(blockers).toContainText('Chưa có lần kiểm tra đạt cho code hiện tại.')
    await expect(blockers).toContainText('Bản sửa đổi tệp cấm')
    await expect(blockers).toContainText('Có commit trên nhánh ghi Claude/Anthropic')
    await expect(blockers).toContainText('Sửa lại (reword) các commit đó trong worktree')
  })

  test('hides the section when there is no open fix', async ({ page }) => {
    const calls = await mockFixes(page, { items: [] })
    await pickWorkflow(page)
    await expect(page.locator('.check-item').first()).toBeVisible()
    expect(calls.list).toBeGreaterThan(0)
    await expect(section(page)).toHaveCount(0)
  })

  test('a failed list shows a compact error with a working retry', async ({ page, guard }) => {
    guard.allow(/platform-fixes|Failed to load resource/)
    await mockFixes(page, { listFails: 1 })
    await pickWorkflow(page)
    const alert = section(page).getByRole('alert')
    await expect(alert).toContainText('Không tải được danh sách bản sửa nền tảng')
    await alert.getByRole('button', { name: 'Thử lại' }).click()
    await expect(section(page).locator('.pfi')).toHaveCount(2)
  })

  test('verify again polls while running, offers cancel, and ends mergeable', async ({ page }) => {
    const calls = await mockFixes(page)
    await pickWorkflow(page)
    const blocked = itemOf(page, BLOCKED)
    await blocked.getByRole('button', { name: 'Kiểm tra lại' }).click()
    await expect(blocked).toContainText('Đang kiểm tra…')
    await expect(blocked.getByRole('button', { name: 'Huỷ kiểm tra' })).toBeVisible()
    await expect(blocked.getByRole('button', { name: MERGE })).toBeDisabled()
    await expect(blocked).toContainText('Kiểm tra đạt', { timeout: 15_000 })
    await expect(blocked.getByRole('button', { name: MERGE })).toBeEnabled()
    await expect(blocked.locator('.pfi-blockers')).toHaveCount(0)
    expect(calls.verify).toEqual([BLOCKED.id])
  })

  test('cancel stops a running verify', async ({ page }) => {
    const calls = await mockFixes(page)
    await pickWorkflow(page)
    const blocked = itemOf(page, BLOCKED)
    await blocked.getByRole('button', { name: 'Kiểm tra lại' }).click()
    await blocked.getByRole('button', { name: 'Huỷ kiểm tra' }).click()
    await expect(blocked).toContainText('Đã huỷ kiểm tra')
    await expect(blocked.getByRole('button', { name: 'Kiểm tra lại' })).toBeVisible()
    expect(calls.cancel).toEqual([BLOCKED.id])
  })

  test('merge: states what happens, wrong password is cleared, then success lists actions and next steps', async ({ page, guard }) => {
    guard.allow(/platform-fixes|Failed to load resource/)
    const calls = await mockFixes(page)
    await pickWorkflow(page)
    const dialog = await openMerge(page)
    await expect(dialog).toContainText('Commit 3 thay đổi đang có trong worktree bằng tên tác giả git của bạn.')
    await expect(dialog).toContainText(`Merge --no-ff nhánh ${OK.branch} vào main.`)
    await expect(dialog).toContainText(`Xoá thư mục worktree ${OK.worktree}.`)
    await expect(dialog).toContainText(`Xoá nhánh ${OK.branch}.`)
    await expect(dialog).toContainText('Không push gì lên remote.')
    await expect(dialog).toContainText('khởi động lại máy chủ AgentDev')

    const confirm = dialog.getByRole('button', { name: 'Commit + merge', exact: true })
    const password = dialog.locator('input[type="password"]')
    await expect(confirm).toBeDisabled()
    await password.fill('wrong')
    await expect(confirm).toBeDisabled()
    await dialog.getByRole('checkbox').check()
    await dialog.getByLabel('Thông điệp commit (không bắt buộc)').fill('fix(engine): stop the loop')
    await confirm.click()
    await expect(dialog.getByRole('alert')).toContainText('Sai mật khẩu, còn 4 lần thử')
    await expect(password).toHaveValue('')
    await expect(confirm).toBeDisabled()

    await password.fill('right')
    await confirm.click()
    const done = dialog.locator('.pfs-done')
    await expect(done).toContainText('Đã merge vào main.')
    await expect(done).toContainText(`Đã commit aaaaaaaaaa trên nhánh ${OK.branch}: fix(engine): stop the loop`)
    await expect(done).toContainText(`Đã merge ${OK.branch} vào main (bbbbbbbbbb).`)
    await expect(done).toContainText(`Đã xoá nhánh ${OK.branch}.`)
    await expect(done).toContainText('Khởi động lại máy chủ AgentDev để chạy code mới.')
    await expect(done).toContainText('AgentDev không push')
    expect(calls.merge).toEqual([
      { password: 'wrong', confirm: true, message: 'fix(engine): stop the loop' },
      { password: 'right', confirm: true, message: 'fix(engine): stop the loop' }
    ])
    await expect(itemOf(page, OK)).toHaveCount(0)
    await dialog.getByRole('button', { name: 'Đóng' }).first().click()
    await expect(dialog).toHaveCount(0)
  })

  test('merge refused by a blocker explains it and how to fix it', async ({ page, guard }) => {
    guard.allow(/platform-fixes|Failed to load resource/)
    await mockFixes(page, { mergeRefusal: err(409, 'ai_attribution', { blockers: ['ai_attribution'], commits: ['abcdef0123456789'] }) })
    await pickWorkflow(page)
    const dialog = await openMerge(page)
    await dialog.getByRole('checkbox').check()
    await dialog.locator('input[type="password"]').fill('right')
    await dialog.getByRole('button', { name: 'Commit + merge', exact: true }).click()
    const alert = dialog.getByRole('alert')
    await expect(alert).toContainText('Chưa merge được: Có commit trên nhánh ghi Claude/Anthropic')
    await expect(alert).toContainText('reword')
    await expect(alert).toContainText('abcdef0123')
    await expect(itemOf(page, OK)).toHaveCount(1)
  })

  test('closing the dialog forgets the password and the confirmation', async ({ page }) => {
    await mockFixes(page)
    await pickWorkflow(page)
    let dialog = await openMerge(page)
    await dialog.getByRole('checkbox').check()
    await dialog.locator('input[type="password"]').fill('secret')
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    dialog = await openMerge(page)
    await expect(dialog.locator('input[type="password"]')).toHaveValue('')
    await expect(dialog.getByRole('checkbox')).not.toBeChecked()
  })

  test('discard: states what is deleted, needs checkbox + password, then removes the fix', async ({ page }) => {
    const calls = await mockFixes(page)
    await pickWorkflow(page)
    await itemOf(page, BLOCKED).getByRole('button', { name: 'Bỏ bản sửa' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toContainText(`Xoá hẳn nhánh ${BLOCKED.branch}, kể cả commit chưa merge.`)
    await expect(dialog).toContainText('Không hoàn tác được.')
    await expect(dialog.getByLabel('Thông điệp commit (không bắt buộc)')).toHaveCount(0)
    const confirm = dialog.getByRole('button', { name: 'Bỏ bản sửa', exact: true })
    await expect(confirm).toBeDisabled()
    await dialog.getByRole('checkbox').check()
    await dialog.locator('input[type="password"]').fill('right')
    await confirm.click()
    await expect(dialog.locator('.pfs-done')).toContainText('Đã bỏ bản sửa.')
    await expect(dialog.locator('.pfs-done')).toContainText(`Đã xoá worktree ${BLOCKED.worktree}.`)
    expect(calls.discard).toEqual([{ password: 'right', confirm: true }])
    await expect(itemOf(page, BLOCKED)).toHaveCount(0)
  })
})

// --- axe: section, dialogs, done state, list error; 375 + 1440, light + dark ---
const KNOWN = new Set([])
const STATES = [
  {
    name: 'section',
    open: async (page) => {
      await mockFixes(page)
      await pickWorkflow(page)
      const blocked = itemOf(page, BLOCKED)
      await blocked.locator('.pfi-tail summary').first().click()
      await blocked.getByText('2 tệp đã đổi').click()
      await itemOf(page, OK).getByText('Báo cáo ngắn').click()
      await expect(itemOf(page, OK).getByLabel('Báo cáo ngắn')).toBeVisible()
    },
    scope: '.pfs'
  },
  {
    name: 'list-error',
    errors: [/platform-fixes|Failed to load resource/],
    open: async (page) => {
      await mockFixes(page, { listFails: 99 })
      await pickWorkflow(page)
      await expect(section(page).getByRole('alert')).toBeVisible()
    },
    scope: '.pfs'
  },
  {
    name: 'merge-dialog-error',
    errors: [/platform-fixes|Failed to load resource/],
    open: async (page) => {
      await mockFixes(page)
      await pickWorkflow(page)
      const dialog = await openMerge(page)
      await dialog.getByRole('checkbox').check()
      await dialog.locator('input[type="password"]').fill('wrong')
      await dialog.getByRole('button', { name: 'Commit + merge', exact: true }).click()
      await expect(dialog.getByRole('alert')).toBeVisible()
    },
    scope: '[role="dialog"]'
  },
  {
    name: 'merge-dialog-done',
    open: async (page) => {
      await mockFixes(page)
      await pickWorkflow(page)
      const dialog = await openMerge(page)
      await dialog.getByRole('checkbox').check()
      await dialog.locator('input[type="password"]').fill('right')
      await dialog.getByRole('button', { name: 'Commit + merge', exact: true }).click()
      await expect(dialog.locator('.pfs-done')).toBeVisible()
    },
    scope: '[role="dialog"]'
  },
  {
    name: 'discard-dialog',
    open: async (page) => {
      await mockFixes(page)
      await pickWorkflow(page)
      await itemOf(page, BLOCKED).getByRole('button', { name: 'Bỏ bản sửa' }).click()
      await expect(page.getByRole('dialog')).toBeVisible()
    },
    scope: '[role="dialog"]'
  }
]

for (const theme of ['light', 'dark']) {
  for (const [width, height] of [[375, 812], [1440, 900]]) {
    for (const state of STATES) {
      test(`axe lab platform fixes ${state.name} ${width} ${theme}`, async ({ page, guard }) => {
        for (const rule of state.errors || []) guard.allow(rule)
        await page.setViewportSize({ width, height })
        await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
        await page.addInitScript(([t]) => {
          try {
            localStorage.setItem('agent_config_settings', JSON.stringify({ THEME: t, LANGUAGE: 'vi', ENABLE_HELP_TOOLTIPS: true }))
          } catch { /* storage blocked */ }
        }, [theme])
        await state.open(page)
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
        await page.locator(state.scope).first().scrollIntoViewIfNeeded()
        if (SHOTS) {
          const base = path.join(SHOTS, `pf-${state.name}-${width}-${theme}`)
          await page.screenshot({ path: `${base}.png` })
          await page.locator(state.scope).first().screenshot({ path: `${base}-el.png` })
        }

        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
        expect(overflow, 'horizontal page scroll (px)').toBeLessThanOrEqual(0)

        if (width < 600) {
          const small = await page.locator(state.scope).first().evaluate((root) =>
            [...root.querySelectorAll('button, a[href], summary, input[type="checkbox"]')]
              .map((el) => ({ el, r: el.getBoundingClientRect() }))
              .filter(({ r }) => r.width && r.height < 44)
              .map(({ el, r }) => `${el.tagName.toLowerCase()} "${(el.textContent || el.type).trim().slice(0, 30)}" ${Math.round(r.height)}px`)
          )
          if (small.length) console.log(`[tap lab-pf ${state.name} ${width} ${theme}] ${small.join(' | ')}`)
        }

        const results = await new AxeBuilder({ page })
          .include(state.scope)
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
          .analyze()
        const summary = results.violations.map((v) => `${v.impact} ${v.id} x${v.nodes.length}: ${v.nodes[0]?.target?.join(' ')} ${v.nodes[0]?.any?.[0]?.message || ''}`)
        if (summary.length) console.log(`[axe lab-pf ${state.name} ${width} ${theme}]\n  ${summary.join('\n  ')}`)
        const blocking = results.violations.filter((v) => ['critical', 'serious'].includes(v.impact) && !KNOWN.has(`${state.name}:${v.id}`))
        expect(blocking.map((v) => `${v.id}: ${v.help}`), 'critical/serious a11y violations').toEqual([])
      })
    }
  }
}

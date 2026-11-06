/* global process */
// WCAG 2.x A/AA scan of the Lab root-cause states (findings by layer, platform-fix dialog, rerun
// compare table, assistant rerun card), light + dark, 375 + 1440. Critical/serious violations fail,
// as in axe.spec.js; so does a horizontal page scroll at any width. Jobs, platform-fix and rerun
// endpoints are mocked: nothing runs, spends tokens or reaches the real platform-fix endpoint.
// E2E_SHOTS=<dir> also saves a viewport and an element screenshot of every state there (for a visual review).
import path from 'node:path'
import AxeBuilder from '@axe-core/playwright'
import { test, expect } from './helpers/fixture.js'
import { WORKFLOW_FILE, WORKFLOW_ID } from './helpers/workflow.js'
import { FIX_INFO, JOB, JOB_MIXED, runJob } from './helpers/lab.js'

const THEMES = ['light', 'dark']
const WIDTHS = [[375, 812], [1440, 900]]
const SHOTS = process.env.E2E_SHOTS || ''
// Rule ids accepted for now, keyed "state:rule". Keep empty.
const KNOWN = new Set([])

const FIX_RESULT = {
  branch: 'platform-fix/e2elabjob0001',
  worktree: 'D:/Code/Tuyen/agentdev-platform-fix-worktrees/e2elabjob0001-very-long-folder-name/backend',
  brief_file: 'D:/Code/Tuyen/agentdev-platform-fix-worktrees/e2elabjob0001-very-long-folder-name/PLATFORM_FIX.md',
  actions: [{ code: 'created_branch', text: 'Created branch', params: { branch: 'platform-fix/e2elabjob0001', head: '0123456789abcdef' } }],
  next_steps: [{ code: 'open_worktree', text: 'Open the worktree', params: { path: 'D:/Code/Tuyen/agentdev-platform-fix-worktrees/e2elabjob0001-very-long-folder-name' } }]
}

const RERUN = {
  ...JOB,
  id: 'e2elabrerun02',
  rerun_of: JOB.id,
  rerun_scenarios: [0],
  rerun_compare: {
    before: { pass_rate: 0, avg_seconds: 10, cost_usd: 0.04, done: 4 },
    after: { pass_rate: 1, avg_seconds: 11, cost_usd: 0.026, done: 2 },
    flags: { cost_usd: { was: 0.01, now: 0.013, per_run: true } }
  }
}
const ESTIMATE = { scenarios: [0, 2], runs: 4, cost_known: true, estimate_usd: 0.052 }

async function openPlatformFix(page, { info = 'ok', submit = false } = {}) {
  await page.route('**/api/lab/platform-fix/info', (route) =>
    info === 'ok' ? route.fulfill({ json: FIX_INFO }) : route.fulfill({ status: 500, json: { detail: 'boom' } })
  )
  // Never the real endpoint: a password sent there could prepare a real branch.
  await page.route(`**/api/lab/jobs/*/platform-fix`, (route) => route.fulfill({ json: FIX_RESULT }))
  await runJob(page, JOB_MIXED)
  await page.getByRole('button', { name: 'Yêu cầu sửa mã nguồn…' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  if (info !== 'ok') {
    await expect(dialog.getByRole('alert')).toBeVisible()
    return
  }
  await expect(dialog.locator('.pf-form')).toBeVisible()
  if (!submit) return
  await dialog.locator('input[type="password"]').fill('mocked')
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: 'Xác nhận và chuẩn bị' }).click()
  await expect(dialog.locator('.pf-done')).toBeVisible()
}

async function openRerunCard(page, { fail = false } = {}) {
  await page.route(`**/api/lab/jobs/${JOB.id}/rerun-failed/estimate`, (route) =>
    fail ? route.fulfill({ status: 500, json: { detail: 'boom' } }) : route.fulfill({ json: ESTIMATE })
  )
  await page.goto(`/workflows/${WORKFLOW_ID}`)
  await page.getByRole('button', { name: 'Mở trợ lý quy trình' }).click()
  await expect(page.locator('.panel-context')).toBeVisible()
  // The offer appears after a Lab-seeded fix was applied; set that state directly on the shared
  // composable (same module instance as the app) instead of driving a real assistant reply.
  await page.evaluate(async ([labJobId, workflow]) => {
    const mod = await import('/src/composables/useWorkflowAssistant.js')
    mod.useWorkflowAssistant().rerunOffer.value = { labJobId, workflow }
  }, [JOB.id, WORKFLOW_ID])
  const card = page.locator('.rerun-card')
  await expect(card).toBeVisible()
  if (fail) await expect(card.getByRole('alert')).toBeVisible()
  else await expect(card.locator('.rerun-summary')).toBeVisible()
}

const STATES = [
  {
    name: 'diagnosis-layers',
    errors: [],
    open: async (page) => {
      await runJob(page, JOB_MIXED)
      await expect(page.locator('.diag-layer-title')).toHaveCount(4)
      await expect(page.locator('.layer-environment .env-hints')).toBeVisible()
      await page.getByText('Xem báo cáo lỗi nền tảng').click()
      await expect(page.locator('.pf-pre')).toBeVisible()
    },
    scope: '.diagnosis'
  },
  { name: 'platform-fix-info', open: (page) => openPlatformFix(page), scope: '[role="dialog"]' },
  {
    name: 'platform-fix-error',
    errors: [/platform-fix|Failed to load resource/],
    open: (page) => openPlatformFix(page, { info: 'error' }),
    scope: '[role="dialog"]'
  },
  { name: 'platform-fix-done', open: (page) => openPlatformFix(page, { submit: true }), scope: '[role="dialog"]' },
  {
    name: 'rerun-compare',
    open: async (page) => {
      for (const job of [JOB, RERUN]) {
        await page.route(`**/api/lab/jobs/${job.id}`, (route) => route.fulfill({ json: job }))
        await page.route(`**/api/lab/jobs/${job.id}/products`, (route) => route.fulfill({ json: { runs: [] } }))
        await page.route(`**/api/lab/jobs/${job.id}/runs/*/files`, (route) => route.fulfill({ json: { files: [] } }))
      }
      await page.goto(`/lab?workflow=${WORKFLOW_FILE}&job=${RERUN.id}`)
      await expect(page.locator('.rerun-compare tbody tr')).toHaveCount(3)
    },
    scope: '.rerun-compare'
  },
  { name: 'rerun-card-estimate', open: (page) => openRerunCard(page), scope: '.rerun-card' },
  {
    name: 'rerun-card-error',
    errors: [/rerun-failed|Failed to load resource/],
    open: (page) => openRerunCard(page, { fail: true }),
    scope: '.rerun-card'
  }
]

for (const theme of THEMES) {
  for (const [width, height] of WIDTHS) {
    for (const state of STATES) {
      test(`axe lab ${state.name} ${width} ${theme}`, async ({ page, guard }) => {
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
          const base = path.join(SHOTS, `${state.name}-${width}-${theme}`)
          await page.screenshot({ path: `${base}.png` })
          await page.locator(state.scope).first().screenshot({ path: `${base}-el.png` })
        }

        // No horizontal page scroll, at 375 px especially.
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
        expect(overflow, 'horizontal page scroll (px)').toBeLessThanOrEqual(0)

        if (width < 600) {
          // Report-only: tap targets under the 44 px project convention.
          const small = await page.locator(state.scope).first().evaluate((root) =>
            [...root.querySelectorAll('button, a[href], summary, input[type="checkbox"]')]
              .map((el) => ({ el, r: el.getBoundingClientRect() }))
              .filter(({ r }) => r.width && r.height < 44)
              .map(({ el, r }) => `${el.tagName.toLowerCase()} "${(el.textContent || el.type).trim().slice(0, 30)}" ${Math.round(r.height)}px`)
          )
          if (small.length) console.log(`[tap lab ${state.name} ${width} ${theme}] ${small.join(' | ')}`)
        }

        const results = await new AxeBuilder({ page })
          .include(state.scope)
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
          .analyze()
        const summary = results.violations.map((v) => `${v.impact} ${v.id} x${v.nodes.length}: ${v.nodes[0]?.target?.join(' ')} ${v.nodes[0]?.any?.[0]?.message || ''}`)
        if (summary.length) console.log(`[axe lab ${state.name} ${width} ${theme}]\n  ${summary.join('\n  ')}`)
        const blocking = results.violations.filter(
          (v) => ['critical', 'serious'].includes(v.impact) && !KNOWN.has(`${state.name}:${v.id}`)
        )
        expect(blocking.map((v) => `${v.id}: ${v.help}`), 'critical/serious a11y violations').toEqual([])
      })
    }
  }
}

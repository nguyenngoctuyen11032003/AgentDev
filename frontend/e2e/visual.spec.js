// Visual snapshots: 8 pages x 4 widths x 2 themes. Run alone with `npm run e2e:visual`,
// refresh baselines with `npm run e2e:visual:update`. Baselines live in e2e/visual.spec.js-snapshots/
// (platform suffix included), so they are per machine/OS; review the diff before accepting an update.
import { test, expect, FREEZE_CSS } from './helpers/fixture.js'
import { API, buildYaml, pickConnection, WORKFLOW_ID } from './helpers/workflow.js'
import { mockConnections, mockSkills } from './helpers/mocks.js'

// Own workflow with a fixed name, so snapshots never depend on E2E_WORKFLOW_ID or on other suites.
const VISUAL_ID = 'zz_e2e_visual'
const VISUAL_FILE = `${VISUAL_ID}.yaml`
const WIDTHS = [
  [375, 812],
  [768, 1024],
  [1024, 768],
  [1440, 900],
]
const THEMES = ['light', 'dark']
const FIXED_TIME = new Date('2026-01-15T09:00:00Z')

const PAGES = [
  { name: 'home', url: '/', ready: '.home-view .title', mask: ['.backdrop'] },
  { name: 'tutorial', url: '/tutorial', ready: '.markdown-body h1' },
  { name: 'workflow', url: `/workflows/${VISUAL_ID}`, ready: '.vue-flow__node', mask: ['#workflow-sidebar'] },
  { name: 'launch', url: `/launch?workflow=${VISUAL_FILE}`, ready: '.composer-send', mask: ['.sessions-rail', '.session-sidebar', '[class*="sessions-panel"]'] },
  { name: 'lab', url: '/lab', ready: '.intro-step' },
  { name: 'settings-general', url: '/settings/general', ready: '.general-settings' },
  { name: 'settings-connections', url: '/settings/connections', ready: '.connection-card', mocks: 'connections' },
  { name: 'settings-skills', url: '/settings/skills', ready: '.skill-card', mocks: 'skills' },
]

test.use({ allowedErrors: [/\/api\/(skills|connections)/] })

test.beforeAll(async ({ request }) => {
  const picked = (await pickConnection(request)) || { connection: 'none', provider: 'anthropic' }
  await request.delete(`${API}/api/workflows/${VISUAL_FILE}/delete`).catch(() => {})
  const content = buildYaml(picked).replaceAll(WORKFLOW_ID, VISUAL_ID)
  const res = await request.post(`${API}/api/workflows/upload/content`, { data: { filename: VISUAL_FILE, content } })
  if (!res.ok()) throw new Error(`create visual workflow failed: ${res.status()}`)
})

test.afterAll(async ({ request }) => {
  await request.delete(`${API}/api/workflows/${VISUAL_FILE}/delete`).catch(() => {})
})

for (const theme of THEMES) {
  for (const [width, height] of WIDTHS) {
    for (const spec of PAGES) {
      test(`visual ${spec.name} ${width} ${theme}`, async ({ page }) => {
        await page.setViewportSize({ width, height })
        await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
        await page.clock.setFixedTime(FIXED_TIME)
        await page.addInitScript(([t]) => {
          try {
            localStorage.setItem('agent_config_settings', JSON.stringify({ THEME: t, LANGUAGE: 'vi', ENABLE_HELP_TOOLTIPS: true }))
          } catch { /* storage blocked */ }
        }, [theme])
        if (spec.mocks === 'connections') await mockConnections(page)
        if (spec.mocks === 'skills') {
          await mockSkills(page, [
            { name: 'cto-management', description: 'Dung khi lap ke hoach ky thuat' },
            { name: 'code-review', description: 'Dung khi review code truoc khi merge' },
            { name: 'broken-skill', description: '', valid: false, error: 'Thieu frontmatter' },
          ])
        }

        await page.goto(spec.url)
        await expect(page.locator(spec.ready).first()).toBeVisible()
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
        await page.addStyleTag({ content: FREEZE_CSS })
        await page.evaluate(() => document.fonts.ready)
        await page.waitForLoadState('networkidle').catch(() => {})
        await page.mouse.move(0, 0)

        await expect(page).toHaveScreenshot(`${spec.name}-${width}-${theme}.png`, {
          animations: 'disabled',
          caret: 'hide',
          maxDiffPixelRatio: 0.02,
          mask: (spec.mask || []).map((s) => page.locator(s)),
        })
      })
    }
  }
}

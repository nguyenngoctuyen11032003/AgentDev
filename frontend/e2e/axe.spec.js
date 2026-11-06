// Automated WCAG 2.x A/AA scan of the 8 pages (light + dark, 375 + 1440). Fails on critical/serious
// violations that are not in KNOWN. Moderate/minor ones are printed, not failed. Run: npm run e2e:axe
import AxeBuilder from '@axe-core/playwright'
import { test, expect } from './helpers/fixture.js'
import { API, buildYaml, pickConnection, WORKFLOW_ID } from './helpers/workflow.js'
import { mockConnections, mockSkills } from './helpers/mocks.js'

const AXE_ID = 'zz_e2e_axe'
const AXE_FILE = `${AXE_ID}.yaml`
const THEMES = ['light', 'dark']
const WIDTHS = [[375, 812], [1440, 900]]
// Rule ids accepted for now (documented backlog), keyed "page:rule". Keep this list short and shrinking.
const KNOWN = new Set([])

const PAGES = [
  { name: 'home', url: '/', ready: '.home-view .title' },
  { name: 'tutorial', url: '/tutorial', ready: '.markdown-body h1' },
  { name: 'workflow', url: `/workflows/${AXE_ID}`, ready: '.vue-flow__node' },
  { name: 'launch', url: `/launch?workflow=${AXE_FILE}`, ready: '.composer-send' },
  { name: 'lab', url: '/lab', ready: '.intro-step' },
  { name: 'settings-general', url: '/settings/general', ready: '.general-settings' },
  { name: 'settings-connections', url: '/settings/connections', ready: '.connection-card', mocks: 'connections' },
  { name: 'settings-skills', url: '/settings/skills', ready: '.skill-card', mocks: 'skills' },
]

test.use({ allowedErrors: [/\/api\/(skills|connections)/] })

test.beforeAll(async ({ request }) => {
  const picked = (await pickConnection(request)) || { connection: 'none', provider: 'anthropic' }
  await request.delete(`${API}/api/workflows/${AXE_FILE}/delete`).catch(() => {})
  const content = buildYaml(picked).replaceAll(WORKFLOW_ID, AXE_ID)
  const res = await request.post(`${API}/api/workflows/upload/content`, { data: { filename: AXE_FILE, content } })
  if (!res.ok()) throw new Error(`create axe workflow failed: ${res.status()}`)
})

test.afterAll(async ({ request }) => {
  await request.delete(`${API}/api/workflows/${AXE_FILE}/delete`).catch(() => {})
})

for (const theme of THEMES) {
  for (const [width, height] of WIDTHS) {
    for (const spec of PAGES) {
      test(`axe ${spec.name} ${width} ${theme}`, async ({ page }) => {
        await page.setViewportSize({ width, height })
        await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
        await page.addInitScript(([t]) => {
          try {
            localStorage.setItem('agent_config_settings', JSON.stringify({ THEME: t, LANGUAGE: 'vi', ENABLE_HELP_TOOLTIPS: true }))
          } catch { /* storage blocked */ }
        }, [theme])
        if (spec.mocks === 'connections') await mockConnections(page)
        if (spec.mocks === 'skills') {
          await mockSkills(page, [
            { name: 'cto-management', description: 'Dung khi lap ke hoach ky thuat' },
            { name: 'broken-skill', description: '', valid: false, error: 'Thieu frontmatter' },
          ])
        }
        await page.goto(spec.url)
        await expect(page.locator(spec.ready).first()).toBeVisible()
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
        await page.waitForLoadState('networkidle').catch(() => {})
        const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
        const summary = results.violations.map((v) => `${v.impact} ${v.id} x${v.nodes.length}: ${v.nodes[0]?.target?.join(' ')}`)
        if (summary.length) console.log(`[axe ${spec.name} ${width} ${theme}]\n  ${summary.join('\n  ')}`)
        const blocking = results.violations.filter(
          (v) => ['critical', 'serious'].includes(v.impact) && !KNOWN.has(`${spec.name}:${v.id}`),
        )
        expect(blocking.map((v) => `${v.id}: ${v.help}`), 'critical/serious a11y violations').toEqual([])
      })
    }
  }
}

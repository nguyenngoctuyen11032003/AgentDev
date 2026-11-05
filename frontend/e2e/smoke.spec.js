/* global process */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect } from '@playwright/test'
import { WORKFLOW_ID, WORKFLOW_FILE } from './helpers/workflow.js'

const here = path.dirname(fileURLToPath(import.meta.url))
const label = (process.env.E2E_LABEL || 'latest').replace(/[^\w.-]/g, '_')
const shotDir = path.join(here, 'artifacts', label)
fs.mkdirSync(shotDir, { recursive: true })

const screens = [
  { name: 'workflow-editor', url: `/workflows/${WORKFLOW_ID}`, ready: '.vue-flow__node' },
  { name: 'lab', url: '/lab', ready: 'main, #app' },
  { name: 'launch', url: `/launch?workflow=${WORKFLOW_FILE}`, ready: '.composer-send' },
]

for (const width of [375, 1024, 1440]) {
  for (const screen of screens) {
    test(`smoke ${screen.name} @${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: width < 600 ? 800 : 900 })
      const errors = []
      page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`) })
      page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
      page.on('response', (r) => { if (r.status() >= 500) errors.push(`http ${r.status()}: ${r.url()}`) })

      await page.goto(screen.url)
      await page.locator(screen.ready).first().waitFor({ state: 'visible' })
      await page.waitForLoadState('networkidle').catch(() => {})
      await page.waitForTimeout(800)

      await page.screenshot({ path: path.join(shotDir, `${screen.name}-${width}.png`), fullPage: false })

      const overflow = await page.evaluate(() => ({
        scroll: document.documentElement.scrollWidth,
        client: document.documentElement.clientWidth,
        body: document.body.scrollWidth,
      }))
      expect(overflow.scroll, `horizontal overflow ${JSON.stringify(overflow)}`).toBeLessThanOrEqual(overflow.client)
      expect(errors, errors.join('\n')).toEqual([])
    })
  }
}

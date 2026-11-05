// Shared Playwright `test`: every test fails at teardown when the page logged a console error,
// threw an uncaught error, or got a 4xx/5xx response, unless the test lists it as allowed.
//   test.use({ allowedErrors: [/\/api\/skills/, 404] })   // per file / describe
//   test('x', async ({ page, guard }) => { guard.allow(/some message/) })  // per test
import { test as base, expect } from '@playwright/test'

const matches = (rule, entry) => {
  if (rule instanceof RegExp) return rule.test(entry.text)
  if (typeof rule === 'number') return entry.status === rule
  return entry.text.includes(String(rule))
}

export const test = base.extend({
  // Array of RegExp (tested against "console: ... | pageerror: ... | http 500: url"), numbers (HTTP status) or substrings.
  allowedErrors: [[], { option: true }],
  guard: [
    async ({ page, allowedErrors }, use) => {
      const seen = []
      const extra = []
      page.on('console', (m) => {
        if (m.type() === 'error') seen.push({ text: `console: ${m.text()} (${m.location().url || ''})` })
      })
      page.on('pageerror', (e) => seen.push({ text: `pageerror: ${e.message}` }))
      page.on('response', (r) => {
        if (r.status() >= 400) seen.push({ text: `http ${r.status()}: ${r.request().method()} ${r.url()}`, status: r.status() })
      })
      await use({ allow: (rule) => extra.push(rule), seen })
      const bad = seen.filter((e) => ![...allowedErrors, ...extra].some((rule) => matches(rule, e)))
      expect(bad.map((e) => e.text), 'unexpected console/page/http errors').toEqual([])
    },
    { auto: true },
  ],
})

export { expect }

// Disable animations and transitions so screenshots and clicks are stable.
export const FREEZE_CSS = `*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important;scroll-behavior:auto!important}`

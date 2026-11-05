import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'

const read = (rel) => readFileSync(new URL(rel, import.meta.url), 'utf8')

describe('Lab screen structure', () => {
  const lab = read('./LabView.vue')

  it('offers a link to run the workflow for real on /launch', () => {
    expect(lab).toMatch(/\/launch/)
    expect(lab).toContain('lab.run_for_real')
  })

  it('does not decide the interrupted state by comparing error text', () => {
    expect(lab).not.toMatch(/startsWith\('interrupted'\)/)
  })

  it('shows API errors through errText (translated by code), never the raw message', () => {
    expect(lab).not.toMatch(/checkError\.value = error\.message/)
    expect(lab).not.toMatch(/listError\.value = error\?\.message/)
    expect(lab).not.toMatch(/evalError\.value = err\?\.message/)
  })

  it('estimates the cost from the server average of graded runs', () => {
    expect(lab).toContain('avg_run_cost_usd')
  })

  it('LabRunPreview has no hard-coded Vietnamese fallbacks', () => {
    const preview = read('../components/lab/LabRunPreview.vue')
    expect(preview).not.toMatch(/\btr\(/)
    expect(preview).not.toMatch(/label: '(Máy|Điện)/)
  })

  it('LabHistory can delete a stored evaluation', () => {
    expect(read('../components/lab/LabHistory.vue')).toContain('labDeleteJob')
    expect(read('../api/client.js')).toMatch(/export const labDeleteJob/)
  })
})

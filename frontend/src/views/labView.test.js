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

  it('remounts the platform fix per job and drops a confirm answer for a job no longer shown', () => {
    expect(lab).toMatch(/<LabPlatformFix[^>]*:key="job\.id"/)
    const fix = read('../components/lab/LabPlatformFix.vue')
    expect(fix).toMatch(/const jobId = props\.jobId/)
    expect(fix).toMatch(/props\.jobId !== jobId/)
  })

  it('hides the per-run fix only for a completed job the server says needs no workflow fix', () => {
    expect(lab).toContain('canFixRun(job, r)')
    expect(lab).not.toMatch(/job\.needs_workflow_fix !== false" type="button" class="btn secondary sm fix-btn"/)
  })

  it('a ?job= link opens only a job of the shown workflow', () => {
    expect(lab).toMatch(/jobOfWorkflow\(data, name\)/)
    expect(lab).toContain('lab.history.other_workflow')
  })
})


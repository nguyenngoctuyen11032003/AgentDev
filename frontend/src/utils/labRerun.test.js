import { describe, expect, it } from 'vitest'
import { formatRerunValue, rerunCanRetry, rerunCompareRows, rerunError, rerunErrorCode, rerunErrorText } from './labRerun.js'

describe('rerunCompareRows', () => {
  it('lists the three metrics with got-worse flags', () => {
    const rows = rerunCompareRows({
      before: { pass_rate: 0, avg_seconds: 10, cost_usd: 0.02, done: 2 },
      after: { pass_rate: 1, avg_seconds: 20, cost_usd: 0.02, done: 2 },
      flags: { avg_seconds: { was: 10, now: 20 } }
    })
    expect(rows).toEqual([
      { key: 'pass_rate', before: 0, after: 1, worse: false, perRun: false },
      { key: 'avg_seconds', before: 10, after: 20, worse: true, perRun: false },
      { key: 'cost_usd', before: 0.01, after: 0.01, worse: false, perRun: true }
    ])
  })

  it('compares cost per run when both sides have done, like the backend flag', () => {
    // Total $0.04 over 4 runs before vs $0.026 over 2 runs after: lower total, but +30% per run.
    const [cost] = rerunCompareRows({
      before: { cost_usd: 0.04, done: 4 },
      after: { cost_usd: 0.026, done: 2 },
      flags: { cost_usd: { was: 0.01, now: 0.013, per_run: true } }
    })
    expect(cost).toEqual({ key: 'cost_usd', before: 0.01, after: 0.013, worse: true, perRun: true })
  })

  it('falls back to cost totals when done is missing on a side', () => {
    const [cost] = rerunCompareRows({ before: { cost_usd: 0.04 }, after: { cost_usd: 0.06, done: 2 }, flags: {} })
    expect(cost).toEqual({ key: 'cost_usd', before: 0.04, after: 0.06, worse: false, perRun: false })
  })

  it('drops metrics missing on both sides and tolerates bad input', () => {
    expect(rerunCompareRows({ before: { pass_rate: 0.5 }, after: {} })).toEqual([
      { key: 'pass_rate', before: 0.5, after: null, worse: false, perRun: false }
    ])
    expect(rerunCompareRows(null)).toEqual([])
    expect(rerunCompareRows({ before: { cost_usd: 'x' }, after: null, flags: null })).toEqual([])
  })
})

describe('formatRerunValue', () => {
  it('formats each metric and unknown values', () => {
    expect(formatRerunValue('pass_rate', 0.666)).toBe('67%')
    expect(formatRerunValue('avg_seconds', 12.4)).toBe('12s')
    expect(formatRerunValue('cost_usd', 0.024)).toBe('$0.024')
    expect(formatRerunValue('cost_usd', 1.5)).toBe('$1.50')
    expect(formatRerunValue('cost_usd', 0.0013)).toBe('$0.0013')
    expect(formatRerunValue('cost_usd', null)).toBe('—')
  })
})

describe('rerunErrorCode', () => {
  it('maps server codes, 404 and network failures', () => {
    expect(rerunErrorCode({ status: 409, code: 'nothing_to_rerun' })).toBe('nothing_to_rerun')
    expect(rerunErrorCode({ status: 400, code: 'confirm_required' })).toBe('confirm_required')
    expect(rerunErrorCode({ status: 404 })).toBe('not_found')
    expect(rerunErrorCode(new TypeError('Failed to fetch'))).toBe('network')
    expect(rerunErrorCode({ status: 500, code: 'boom' })).toBe('failed')
  })
})

describe('rerunError / rerunErrorText', () => {
  const keys = {
    'lab.rerun.errors.failed': 'RERUN FAILED',
    'lab.rerun.errors.not_found': 'RERUN NOT FOUND',
    'lab.rerun.errors.nothing_to_rerun': 'NOTHING',
    'lab.rerun.hints.failed': 'HINT FAILED',
    'lab.rerun.hints.not_found': 'HINT NOT FOUND',
    'lab.rerun.hints.nothing_to_rerun': 'HINT NOTHING',
    'lab.rerun.hints.lab_legacy_job': 'HINT LEGACY',
    'lab.errors.lab_legacy_job': 'LAB LEGACY',
    'lab.errors.lab_job_running': 'LAB RUNNING',
    'lab.errors.lab_workflow_not_found': 'LAB WF NOT FOUND',
    'lab.errors.lab_job_not_found': 'LAB JOB {job_id}'
  }
  const te = (key) => key in keys
  const t = (key, params = {}) => keys[key].replace(/\{(\w+)\}/g, (_, k) => params[k] ?? '')
  const text = (error) => rerunErrorText(rerunError(error), { t, te })

  it('uses the Lab text for server codes without a rerun text, never a wrong generic one', async () => {
    expect(text({ status: 409, code: 'lab_legacy_job' }).title).toBe('LAB LEGACY')
    expect(text({ status: 409, code: 'lab_legacy_job' }).hint).toBe('HINT LEGACY')
    expect(text({ status: 409, code: 'lab_job_running' }).title).toBe('LAB RUNNING')
    expect(text({ status: 409, code: 'lab_job_running' }).hint).toBe('HINT FAILED')
    expect(text({ status: 404, code: 'lab_workflow_not_found' }).title).toBe('LAB WF NOT FOUND')
    expect(text({ status: 404, code: 'lab_job_not_found', params: { job_id: 'j1' } }).title).toBe('LAB JOB j1')
    expect(text({ status: 404, code: 'lab_job_not_found' }).hint).toBe('HINT NOT FOUND')
    expect(text({ status: 409, code: 'nothing_to_rerun' })).toEqual({ title: 'NOTHING', hint: 'HINT NOTHING' })
    expect(text({ status: 500, code: 'boom' })).toEqual({ title: 'RERUN FAILED', hint: 'HINT FAILED' })
  })

  it('hides Retry when retrying cannot help', () => {
    expect(rerunCanRetry(rerunError({ status: 409, code: 'lab_legacy_job' }))).toBe(false)
    expect(rerunCanRetry(rerunError({ status: 409, code: 'nothing_to_rerun' }))).toBe(false)
    expect(rerunCanRetry(rerunError({ status: 409, code: 'lab_job_running' }))).toBe(true)
    expect(rerunCanRetry(rerunError(new TypeError('Failed to fetch')))).toBe(true)
  })
})

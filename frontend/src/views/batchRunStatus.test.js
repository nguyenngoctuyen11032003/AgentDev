import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { BATCH_STATUS, batchStatusLabelKey, batchErrorDetail, isBatchFinished } from './batchRunStatus.js'

const locale = (name) => JSON.parse(readFileSync(new URL(`../i18n/locales/${name}.json`, import.meta.url), 'utf8'))
const lookup = (obj, path) => path.split('.').reduce((o, k) => (o ? o[k] : undefined), obj)

describe('BATCH_STATUS', () => {
  it('has an i18n label in vi/en/zh for every value (no raw status ever reaches the UI)', () => {
    for (const name of ['vi', 'en', 'zh']) {
      const messages = locale(name)
      for (const value of Object.values(BATCH_STATUS)) {
        const key = batchStatusLabelKey(value)
        expect(key, `${value} has a label key`).toBeTruthy()
        expect(typeof lookup(messages, key), `${name}:${key}`).toBe('string')
      }
    }
  })

  it('unknown status maps to the idle label instead of leaking the raw value', () => {
    expect(batchStatusLabelKey('Some raw thing')).toBe(batchStatusLabelKey(BATCH_STATUS.IDLE))
  })

  it('knows which statuses are final', () => {
    expect(isBatchFinished(BATCH_STATUS.COMPLETED)).toBe(true)
    expect(isBatchFinished(BATCH_STATUS.CANCELLED)).toBe(true)
    expect(isBatchFinished(BATCH_STATUS.IN_PROGRESS)).toBe(false)
  })
})

describe('batchErrorDetail', () => {
  it('drops the raw message of a thrown exception', () => {
    expect(batchErrorDetail(new Error('TypeError: x is undefined'))).toBe('')
  })
  it('keeps a backend detail string', () => {
    expect(batchErrorDetail({ detail: 'Workflow not found' })).toContain('Workflow not found')
  })
})

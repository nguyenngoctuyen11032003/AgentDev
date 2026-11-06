import { describe, expect, it } from 'vitest'
import {
  BLOCKER_CODES,
  blockersOf,
  canMerge,
  errorCodeOf,
  errorKeys,
  gatesOf,
  i18nParams,
  isVerifying,
  platformFixErrorText,
  pollDelay,
  refusalItems,
  shortSha,
  statusTone
} from './platformFixes.js'

const passed = { id: 'a', mergeable: true, blockers: [], verify: { status: 'passed', gates: [] } }

describe('platformFixes', () => {
  it('offers merge only for a mergeable item without blockers and without a running verify', () => {
    expect(canMerge(passed)).toBe(true)
    expect(canMerge({ ...passed, mergeable: false })).toBe(false)
    expect(canMerge({ ...passed, blockers: ['main_dirty'] })).toBe(false)
    expect(canMerge({ ...passed, verify: { status: 'running' } })).toBe(false)
    expect(canMerge({ ...passed, mergeable: 'yes' })).toBe(false)
    expect(canMerge(null)).toBe(false)
  })

  it('detects a running verify', () => {
    expect(isVerifying({ verify: { status: 'running' } })).toBe(true)
    expect(isVerifying({ verify: { status: 'passed' } })).toBe(false)
    expect(isVerifying({ verify: null })).toBe(false)
  })

  it('maps gate statuses to tones, unknown ones muted', () => {
    expect(statusTone('passed')).toBe('ok')
    expect(statusTone('failed')).toBe('bad')
    expect(statusTone('timeout')).toBe('bad')
    expect(statusTone('running')).toBe('live')
    expect(statusTone('cancelled')).toBe('warn')
    expect(statusTone('skipped')).toBe('muted')
    expect(statusTone('weird')).toBe('muted')
  })

  it('orders blockers like the server checks them, ai_attribution after brief_committed, unknown codes last', () => {
    expect(BLOCKER_CODES.indexOf('ai_attribution')).toBe(BLOCKER_CODES.indexOf('brief_committed') + 1)
    expect(blockersOf({ blockers: ['future', 'main_dirty', 'ai_attribution', 'verify_required'] })).toEqual([
      'verify_required',
      'ai_attribution',
      'main_dirty',
      'future'
    ])
    expect(blockersOf({})).toEqual([])
  })

  it('orders gates in run order and keeps unknown gates at the end', () => {
    const item = { verify: { gates: [{ code: 'x' }, { code: 'frontend_build' }, { code: 'forbidden_untouched' }] } }
    expect(gatesOf(item).map((g) => g.code)).toEqual(['forbidden_untouched', 'frontend_build', 'x'])
    expect(gatesOf({ verify: null })).toEqual([])
  })

  it('shortens shas and joins arrays for i18n params', () => {
    expect(shortSha('0123456789abcdef')).toBe('0123456789')
    expect(i18nParams({ commit: '0123456789abcdef', files: ['a.py', 'b.py'], commits: ['fedcba9876543210'], n: 2 })).toEqual({
      commit: '0123456789',
      files: 'a.py, b.py',
      commits: 'fedcba9876',
      n: 2
    })
    expect(i18nParams(null)).toEqual({})
  })

  it('normalizes error codes and lists the keys to try', () => {
    expect(errorCodeOf({ code: 'lab_bad_password' })).toBe('bad_password')
    expect(errorCodeOf(new Error('x'))).toBe('')
    expect(errorKeys('bad_password')).toEqual(['lab.platform_fixes.errors.bad_password', 'lab.platform_fix.errors.bad_password'])
    expect(errorKeys('')).toEqual([])
  })

  it('backs off the poll delay up to 10 s', () => {
    expect(pollDelay(0)).toBe(1500)
    expect(pollDelay(1)).toBe(2250)
    expect(pollDelay(20)).toBe(10_000)
  })

  it('lists the files or commits a refusal names', () => {
    expect(refusalItems({ params: { files: ['a'], commits: ['0123456789abcdef'] } })).toEqual(['a', '0123456789'])
    expect(refusalItems({})).toEqual([])
  })
})

describe('platformFixErrorText', () => {
  const known = new Set([
    'lab.platform_fixes.errors.merge_conflict',
    'lab.platform_fix.errors.bad_password'
  ])
  const t = (key, params) => `${key}${params ? JSON.stringify(params) : ''}`
  const te = (key) => known.has(key)
  const fallback = () => 'generic'

  it('prefers the platform_fixes key, joins params', () => {
    const text = platformFixErrorText({ code: 'merge_conflict', params: { files: ['a', 'b'] } }, { t, te, fallback })
    expect(text).toBe('lab.platform_fixes.errors.merge_conflict{"files":"a, b"}')
  })

  it('falls back to the platform_fix key, then the generic text', () => {
    expect(platformFixErrorText({ code: 'lab_bad_password', params: { attempts_left: 2 } }, { t, te, fallback })).toBe(
      'lab.platform_fix.errors.bad_password{"attempts_left":2}'
    )
    expect(platformFixErrorText({ code: 'nope' }, { t, te, fallback })).toBe('generic')
  })

  it('explains a blocker refusal with its fix and the commits it names', () => {
    const text = platformFixErrorText(
      { code: 'ai_attribution', params: { blockers: ['ai_attribution'], commits: ['0123456789abcdef'] } },
      { t, te, fallback }
    )
    expect(text).toContain('lab.platform_fixes.errors.blocked')
    expect(text).toContain('lab.platform_fixes.blockers.ai_attribution.fix')
    expect(text).toContain('"items":"0123456789"')
  })
})

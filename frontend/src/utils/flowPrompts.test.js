import { describe, expect, it } from 'vitest'
import { biblePathFor, flowPromptsText, isFlowPackage } from './flowPrompts.js'

describe('flowPrompts', () => {
  it('recognises only the production package file', () => {
    expect(isFlowPackage('series/tap_1/goi_san_xuat.md')).toBe(true)
    expect(isFlowPackage('goi_san_xuat.md')).toBe(true)
    expect(isFlowPackage('series/tap_1/kich_ban.md')).toBe(false)
    expect(isFlowPackage('series/tap_1/goi_san_xuat.md.bak')).toBe(false)
  })

  it('finds the character bible where the renderer looks for it', () => {
    const files = new Set(['series/ho_so_nhan_vat.md'])
    expect(biblePathFor('series/tap_1/goi_san_xuat.md', (p) => files.has(p))).toBe('series/ho_so_nhan_vat.md')
    expect(biblePathFor('du_an/series/tap_2/goi_san_xuat.md', (p) => p === 'du_an/series/ho_so_nhan_vat.md'))
      .toBe('du_an/series/ho_so_nhan_vat.md')
    expect(biblePathFor('tap_1/goi_san_xuat.md', (p) => p === 'tap_1/ho_so_nhan_vat.md')).toBe('tap_1/ho_so_nhan_vat.md')
    expect(biblePathFor('series/tap_1/goi_san_xuat.md', () => false)).toBe('')
  })

  it('joins every shot into one paste-ready text', () => {
    const shots = [{ number: 1, prompt: 'A' }, { number: 2, prompt: 'B' }]
    expect(flowPromptsText(shots, (s) => `# ${s.number}`)).toBe('# 1\nA\n\n# 2\nB\n')
    expect(flowPromptsText([], (s) => s)).toBe('')
  })
})

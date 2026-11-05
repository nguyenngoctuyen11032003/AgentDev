import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = readFileSync(new URL('./main.css', import.meta.url), 'utf8')

function block(selectorStart) {
  const i = css.indexOf(selectorStart)
  const end = css.indexOf('\n}', i)
  return css.slice(i, end)
}
function tokens(b) {
  const out = {}
  for (const m of b.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{3,6})\b/g)) {
    let h = m[2].slice(1)
    if (h.length === 3) h = [...h].map((c) => c + c).join('')
    out[m[1]] = h
  }
  return out
}
const lum = (h) => {
  const c = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
}
const ratio = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}
const SURFACES = ['bg-base', 'bg-deep', 'bg-deep-2', 'surface-1', 'surface-2', 'surface-2b', 'surface-3', 'surface-4', 'surface-5']

describe('muted text tokens meet 4.5:1 on every surface', () => {
  for (const [name, start] of [['dark', ':root {'], ['light', ':root[data-theme="light"] {']]) {
    const t = tokens(block(start))
    for (let n = 1; n <= 10; n++) {
      it(`${name} --text-muted-${n}`, () => {
        for (const s of SURFACES) {
          expect(ratio(t[`text-muted-${n}`], t[s]), `${s}`).toBeGreaterThanOrEqual(4.5)
        }
      })
    }
  }
})

describe('z-confirm token', () => {
  it('sits between modal and toast', () => {
    const g = (n) => Number(new RegExp(String.raw`--${n}:\s*(\d+)`).exec(css)[1])
    expect(g('z-confirm')).toBeGreaterThan(g('z-modal'))
    expect(g('z-confirm')).toBeLessThan(g('z-toast'))
  })
})

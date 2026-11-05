/* global process */
// Usage: node scripts/check-i18n.mjs [--hardcoded] [--json]
// 1) Missing/extra keys between vi/en/zh locales (recursive, dot paths).
// 2) Keys used in code via t('..') / $t('..') / te( / i18n-t keypath that exist in no locale.
// 3) (--hardcoded) Vietnamese/CJK literals in .vue/.js under views, components, composables (heuristic).
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const src = path.join(root, 'src')
const langs = ['vi', 'en', 'zh']
const wantHard = process.argv.includes('--hardcoded')
const asJson = process.argv.includes('--json')

const flat = (o, p = '', out = new Set()) => {
  for (const [k, v] of Object.entries(o)) {
    const key = p ? `${p}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) flat(v, key, out)
    else out.add(key)
  }
  return out
}
const sets = {}
for (const l of langs) sets[l] = flat(JSON.parse(fs.readFileSync(path.join(src, 'i18n/locales', `${l}.json`), 'utf8')))
const union = new Set(langs.flatMap((l) => [...sets[l]]))
const report = { totals: {}, missing: {}, unusedInCode: 0, undefinedKeys: [], dynamicKeys: 0, hardcoded: [] }
for (const l of langs) {
  report.totals[l] = sets[l].size
  report.missing[l] = [...union].filter((k) => !sets[l].has(k)).sort()
}

const walk = (d, out = []) => {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name)
    if (e.isDirectory()) walk(p, out)
    else if (/\.(vue|js)$/.test(e.name) && !/\.test\.js$/.test(e.name)) out.push(p)
  }
  return out
}
const files = walk(src).filter((f) => !f.includes(`${path.sep}locales${path.sep}`))
const used = new Set()
const keyRe = /(?:\$t|\btr|\bt|\bte|\btm)\(\s*(['"`])([^'"`$]+?)\1/g
const kpRe = /keypath=["']([^"']+)["']/g
for (const f of files) {
  const txt = fs.readFileSync(f, 'utf8')
  for (const m of txt.matchAll(keyRe)) {
    const k = m[2]
    if (!/^[\w-]+(\.[\w-]+)+$/.test(k)) continue
    used.add(k)
    if (!union.has(k)) report.undefinedKeys.push(`${path.relative(root, f)}: ${k}`)
  }
  for (const m of txt.matchAll(kpRe)) { used.add(m[1]); if (!union.has(m[1])) report.undefinedKeys.push(`${path.relative(root, f)}: ${m[1]}`) }
  report.dynamicKeys += [...txt.matchAll(/(?:\$t|\bt)\(\s*`[^`]*\$\{/g)].length
}
report.unusedInCode = [...union].filter((k) => !used.has(k)).length

if (wantHard) {
  const hard = /[\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u1EF9\u3400-\u9FFF]/ // Vietnamese diacritics + CJK
  const eng = />\s*([A-Z][a-z]+(?:\s+[a-z]+){1,})\s*</ // template text like >Save changes<
  for (const f of files.filter((f) => /(views|components|composables)/.test(path.relative(src, f).split(path.sep)[0]))) {
    const lines = fs.readFileSync(f, 'utf8').split('\n')
    let inBlock = false, inStyle = false
    lines.forEach((ln, i) => {
      if (/<style/.test(ln)) inStyle = true
      if (/<\/style>/.test(ln)) { inStyle = false; return }
      if (inStyle) return
      let s = ln
      if (inBlock) { if (s.includes('*/') || s.includes('-->')) inBlock = false; return }
      if (/^\s*(\/\*|<!--)/.test(s) && !/(\*\/|-->)\s*$/.test(s)) { inBlock = true; return }
      s = s.replace(/(^|[^:])\/\/.*$/, '$1').replace(/<!--.*?-->/g, '').replace(/\/\*.*?\*\//g, '')
      if (/^\s*(\*|\/\/)/.test(s)) return
      const viaTr = /\btrc?\(\s*['"`]/.test(s)
      const hit = hard.test(s) ? (viaTr ? 'vi-default-in-tr' : 'vi/zh') : eng.test(s) ? 'en' : null
      {
        if (hit) report.hardcoded.push({ file: path.relative(root, f).split(path.sep).join('/'), line: i + 1, kind: hit, text: ln.trim().slice(0, 110) })
      }
    })
  }
}

if (asJson) { console.log(JSON.stringify(report, null, 1)); process.exit(0) }
console.log('keys per locale:', report.totals)
for (const l of langs) console.log(`missing in ${l}: ${report.missing[l].length}`, report.missing[l].slice(0, 15))
console.log(`keys used in code but defined nowhere: ${report.undefinedKeys.length}`)
report.undefinedKeys.slice(0, 40).forEach((k) => console.log('  ', k))
console.log(`locale keys never referenced literally (may be dynamic): ${report.unusedInCode}; dynamic template keys: ${report.dynamicKeys}`)
if (wantHard) {
  const by = {}
  report.hardcoded.forEach((h) => (by[h.file] = (by[h.file] || 0) + 1))
  console.log(`hardcoded-literal lines: ${report.hardcoded.length} in ${Object.keys(by).length} files`)
  Object.entries(by).sort((a, b) => b[1] - a[1]).slice(0, 10).forEach(([f, n]) => console.log('  ', n, f))
  report.hardcoded.slice(0, 400).forEach((h) => console.log(`${h.file}:${h.line} [${h.kind}] ${h.text}`))
}
process.exit(report.undefinedKeys.length || langs.some((l) => report.missing[l].length) ? 1 : 0)

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const LANGS = ['vi', 'en', 'zh']
const read = (l) => readFileSync(fileURLToPath(new URL(`../../public/tutorial-${l}.md`, import.meta.url)), 'utf8')
const docs = Object.fromEntries(LANGS.map((l) => [l, read(l)]))

const headings = (t) => t.split('\n').filter((l) => /^#{1,6} /.test(l)).map((l) => l.match(/^#+/)[0])
const anchors = (t) => [...t.matchAll(/<a id="([^"]+)">/g)].map((m) => m[1])
const images = (t) => [...t.matchAll(/media\/[\w.-]+/g)].map((m) => m[0])

describe('tutorial content', () => {
  it('keeps vi/en/zh structurally identical', () => {
    for (const l of ['en', 'zh']) {
      expect(headings(docs[l])).toEqual(headings(docs.vi))
      expect(anchors(docs[l])).toEqual(anchors(docs.vi))
      expect(images(docs[l])).toEqual(images(docs.vi))
    }
  })

  it('names the navigation bar consistently (no sidebar)', () => {
    expect(docs.vi).not.toMatch(/thanh bên|thanh trên cùng/)
    expect(docs.en).not.toMatch(/sidebar|top bar/i)
    expect(docs.zh).not.toMatch(/侧边栏|顶栏/)
  })

  it('does not claim the Lab approves every question (paid gates are refused)', () => {
    for (const l of LANGS) expect(docs[l]).toMatch(/paid: true/)
    expect(docs.vi).toMatch(/luôn bị từ chối/)
    expect(docs.en).toMatch(/always refused/)
    expect(docs.zh).toMatch(/始终被拒绝/)
  })

  it('documents the run modes, Products view, end-node rule and assistant', () => {
    for (const l of LANGS) {
      expect(docs[l]).toMatch(/Shift\+Tab/)
      expect(docs[l]).toMatch(/MULTIPLE_END_NODES/)
    }
    expect(docs.vi).toMatch(/\| \*\*Bỏ qua xác nhận\*\*/)
    expect(docs.vi).toMatch(/\| \*\*Sản phẩm\*\*/)
    expect(docs.vi).toMatch(/Trợ lý quy trình/)
    expect(docs.en).toMatch(/\| \*\*Bypass approvals\*\*/)
    expect(docs.en).toMatch(/\| \*\*Products\*\*/)
    expect(docs.zh).toMatch(/\| \*\*跳过确认\*\*/)
    expect(docs.zh).toMatch(/\| \*\*产物\*\*/)
  })
})

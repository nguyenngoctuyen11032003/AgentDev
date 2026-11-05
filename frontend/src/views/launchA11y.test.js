import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'

const read = (rel) => readFileSync(new URL(rel, import.meta.url), 'utf8')

describe('Run page accessibility', () => {
  const launch = read('./LaunchView.vue')
  it('the header state and the composer hint live in regions that are always in the DOM', () => {
    expect(launch).not.toMatch(/<span v-if="selectedFile" class="chat-header-status" role="status"/)
    expect(launch).not.toMatch(/<p v-if="composerHint" class="composer-hint" role="status"/)
    expect(launch).toMatch(/class="chat-header-status" role="status"/)
    expect(launch).toMatch(/<div role="status" class="composer-hint-live"/)
  })
  it('touch controls are at least 44px on narrow / coarse screens', () => {
    const css = read('./launch/styles/narrow.css')
    expect(css).toMatch(/pointer: coarse[\s\S]*\.view-tab[\s\S]*min-height: 44px/)
  })
  it('the session search shows a focus ring on its wrapper (the input has outline: none)', () => {
    expect(read('../components/launch/SessionSidebar.vue')).toContain('.sidebar-search:focus-within { outline: 2px solid')
  })
})

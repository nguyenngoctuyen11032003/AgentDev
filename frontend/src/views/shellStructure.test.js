import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'

const read = (rel) => readFileSync(new URL(rel, import.meta.url), 'utf8')

describe('app shell structure', () => {
  it('keeps the navigation bar on /batch-run (only /launch hides it)', () => {
    const app = read('../App.vue')
    expect(app).toContain("route.path !== '/launch'")
    expect(app).not.toMatch(/route\.path !== '\/launch' && route\.path !== '\/batch-run'/)
  })

  it('SettingsView does not nest a second <main> landmark inside App.vue main', () => {
    expect(read('./SettingsView.vue')).not.toContain('<main')
  })

  it('Home "Bắt đầu" is a real link, not a button with router.push', () => {
    const home = read('./HomeView.vue')
    expect(home).toMatch(/<router-link[^>]*to="\/tutorial"[^>]*get-started-btn/)
    expect(home).not.toContain('goToTutorial')
  })

  it('BatchRunView has no dead SettingsModal and no status string literals', () => {
    const batch = read('./BatchRunView.vue')
    expect(batch).not.toMatch(/import SettingsModal|<SettingsModal/)
    expect(batch).not.toMatch(/status\.value\s*=\s*'/)
    expect(batch).not.toMatch(/status\s*(===|!==)\s*'/)
  })
})

describe('dead toggle AUTO_EXPAND_MESSAGES is gone', () => {
  it.each([
    '../components/settings/GeneralSettings.vue',
    '../components/common/SettingsModal.vue',
    './LaunchView.vue'
  ])('%s does not mention it', (rel) => {
    expect(read(rel)).not.toContain('AUTO_EXPAND_MESSAGES')
  })

  it.each(['vi', 'en', 'zh'])('%s locale has no auto_expand_messages keys', (name) => {
    expect(read(`../i18n/locales/${name}.json`)).not.toContain('auto_expand_messages')
  })
})

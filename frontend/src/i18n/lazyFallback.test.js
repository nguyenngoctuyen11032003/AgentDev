import { describe, it, expect } from 'vitest'
import i18n, { initI18n } from '@/i18n'

describe('i18n fallback locale', () => {
  it('does not download the en fallback at startup, only after a missing key', async () => {
    await initI18n()
    expect(i18n.global.availableLocales).toContain('vi')
    expect(i18n.global.availableLocales).not.toContain('en')

    i18n.global.t('zz.key.that.does.not.exist')
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(i18n.global.availableLocales).toContain('en')
  })
})

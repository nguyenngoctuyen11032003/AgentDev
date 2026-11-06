import { describe, expect, it } from 'vitest'
import { previewSandbox } from './outputSources.js'

describe('previewSandbox', () => {
  const page = 'http://localhost:5173'
  it('lets an app on its own port keep its origin (else Vite modules and localStorage fail: blank page)', () => {
    const sandbox = previewSandbox('http://localhost:47100/', page)
    expect(sandbox).toContain('allow-scripts')
    expect(sandbox).toContain('allow-same-origin')
  })
  it('keeps pages served by AgentDev itself opaque', () => {
    expect(previewSandbox('/api/lab/jobs/x/runs/0/site/index.html', page)).not.toContain('allow-same-origin')
    expect(previewSandbox('http://localhost:5173/api/x', page)).not.toContain('allow-same-origin')
    expect(previewSandbox('', page)).not.toContain('allow-same-origin')
    expect(previewSandbox('javascript:alert(1)', page)).not.toContain('allow-same-origin')
  })
})

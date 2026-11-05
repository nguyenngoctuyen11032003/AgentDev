import { describe, it, expect } from 'vitest'
import { canReconcileLayout } from './layoutSyncGuard.js'

const ok = { workflowName: 'demo', yamlLoadedFor: 'demo', loadError: null, parseError: null, graph: { nodes: [] } }

describe('canReconcileLayout', () => {
  it('allows reconcile when the YAML of this workflow loaded and parsed', () => {
    expect(canReconcileLayout(ok)).toBe(true)
  })

  it('blocks when the YAML failed to load', () => {
    expect(canReconcileLayout({ ...ok, yamlLoadedFor: null, loadError: 'boom' })).toBe(false)
    expect(canReconcileLayout({ ...ok, loadError: 'boom' })).toBe(false)
  })

  it('blocks when the YAML failed to parse', () => {
    expect(canReconcileLayout({ ...ok, parseError: 'bad indent' })).toBe(false)
  })

  it('blocks a graph that still belongs to another workflow', () => {
    expect(canReconcileLayout({ ...ok, yamlLoadedFor: 'previous' })).toBe(false)
  })

  it('blocks a missing or non-object graph', () => {
    expect(canReconcileLayout({ ...ok, graph: undefined })).toBe(false)
    expect(canReconcileLayout({ ...ok, graph: [] })).toBe(false)
    expect(canReconcileLayout({ ...ok, workflowName: '',yamlLoadedFor: '' })).toBe(false)
    expect(canReconcileLayout()).toBe(false)
  })
})

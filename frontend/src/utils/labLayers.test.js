import { describe, expect, it } from 'vitest'
import { groupFindings, layerOf, needsWorkflowFix, platformFixErrorCode, workflowUnchanged } from './labLayers.js'

describe('labLayers', () => {
  it('treats a finding without a known layer as a workflow finding (old jobs)', () => {
    expect(layerOf({})).toBe('workflow')
    expect(layerOf({ layer: 'bogus' })).toBe('workflow')
    expect(layerOf({ layer: 'platform' })).toBe('platform')
    expect(layerOf(null)).toBe('workflow')
  })

  it('groups findings in the fixed layer order, skipping empty layers and keeping order inside a layer', () => {
    const findings = [
      { layer: 'scenario', detail: 's1' },
      { layer: 'platform', detail: 'p1' },
      { detail: 'w-old' },
      { layer: 'environment', detail: 'e1' },
      { layer: 'workflow', detail: 'w2' }
    ]
    const groups = groupFindings(findings)
    expect(groups.map((g) => g.layer)).toEqual(['workflow', 'environment', 'platform', 'scenario'])
    expect(groups[0].findings.map((f) => f.detail)).toEqual(['w-old', 'w2'])
    expect(groupFindings([{ layer: 'environment' }]).map((g) => g.layer)).toEqual(['environment'])
    expect(groupFindings(undefined)).toEqual([])
  })

  it('keeps an empty layer that has guidance or a report to show', () => {
    const groups = groupFindings([{ layer: 'scenario' }], ['platform'])
    expect(groups.map((g) => g.layer)).toEqual(['platform', 'scenario'])
    expect(groups[0].findings).toEqual([])
  })

  it('offers the assistant fix only with a brief and unless the server says no fix is needed', () => {
    expect(needsWorkflowFix({ fix_brief: 'x' })).toBe(true) // old job: no flag
    expect(needsWorkflowFix({ fix_brief: 'x', needs_workflow_fix: true })).toBe(true)
    expect(needsWorkflowFix({ fix_brief: 'x', needs_workflow_fix: false })).toBe(false)
    expect(needsWorkflowFix({ fix_brief: '', needs_workflow_fix: true })).toBe(false)
    expect(needsWorkflowFix(null)).toBe(false)
  })

  it('says the workflow is unchanged only when findings exist and none is a workflow finding', () => {
    expect(workflowUnchanged({ findings: [{ layer: 'environment' }, { layer: 'scenario' }] })).toBe(true)
    expect(workflowUnchanged({ findings: [{ layer: 'environment' }, {}] })).toBe(false)
    expect(workflowUnchanged({ findings: [] })).toBe(false)
    expect(workflowUnchanged({})).toBe(false)
  })

  it('normalizes platform-fix error codes', () => {
    expect(platformFixErrorCode({ code: 'bad_password' })).toBe('bad_password')
    expect(platformFixErrorCode({ code: 'lab_too_many_attempts' })).toBe('too_many_attempts')
    expect(platformFixErrorCode(new Error('x'))).toBe('')
  })
})

describe('canFixRun', () => {
  it('offers the per-run fix for a failed run of a job that is not completed yet', async () => {
    const { canFixRun } = await import('./labLayers.js')
    // The server sends needs_workflow_fix=false until the job is completed: that is not a verdict yet.
    expect(canFixRun({ status: 'running', needs_workflow_fix: false }, { status: 'failed' })).toBe(true)
    expect(canFixRun({ status: 'interrupted', needs_workflow_fix: false }, { status: 'error' })).toBe(true)
    expect(canFixRun({ status: 'completed', needs_workflow_fix: false }, { status: 'failed' })).toBe(false)
    expect(canFixRun({ status: 'completed', needs_workflow_fix: true }, { status: 'failed' })).toBe(true)
    expect(canFixRun({ status: 'completed' }, { status: 'failed' })).toBe(true)
    expect(canFixRun({ status: 'running' }, { status: 'passed' })).toBe(false)
    expect(canFixRun(null, { status: 'failed' })).toBe(false)
  })
})

describe('jobOfWorkflow', () => {
  it('matches a job to the shown workflow whatever the .yaml/.yml suffix', async () => {
    const { jobOfWorkflow } = await import('./labLayers.js')
    expect(jobOfWorkflow({ workflow: 'a.yaml' }, 'a.yaml')).toBe(true)
    expect(jobOfWorkflow({ workflow: 'a' }, 'a.yml')).toBe(true)
    expect(jobOfWorkflow({ workflow: 'b.yaml' }, 'a.yaml')).toBe(false)
    expect(jobOfWorkflow({}, 'a.yaml')).toBe(false)
    expect(jobOfWorkflow(null, 'a.yaml')).toBe(false)
  })
})

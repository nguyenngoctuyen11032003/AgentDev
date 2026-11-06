// "Re-run failed scenarios" offer: set only after a Lab-seeded thread's proposal is applied to the
// same workflow; cleared by Undo or by moving to another workflow.
import { createHash } from 'node:crypto'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const hashOf = (text) => createHash('sha256').update(String(text).replace(/\r\n/g, '\n')).digest('hex')

const files = {}
let proposalFor = 'wf'

vi.mock('@/utils/connectionModels.js', () => ({ modelsForConnection: async () => ({ models: [] }) }))
vi.mock('@/api/client.js', () => ({
  cancelAssistantRequest: async () => ({ success: true }),
  deleteAssistantSession: async () => ({ success: true }),
  fetchAssistantProviders: async () => ({ success: true, providers: [] }),
  fetchAssistantSession: async () => ({ success: false }),
  fetchAssistantSessions: async () => ({ success: true, sessions: [] }),
  saveAssistantSession: async () => ({ success: true, updated_at: 1 }),
  fetchVueGraph: async () => ({ success: false }),
  postVuegraphs: async () => ({ success: true }),
  postYaml: async () => ({ success: true }),
  fetchYaml: async (name) => ({ success: true, content: files[name] ?? '' }),
  updateYaml: async (name, content) => {
    files[name] = content
    return { success: true }
  },
  mergeWorkflowDocument: async (name) => {
    files[name] = 'graph:\n  nodes: []\n'
    return { success: true, content: files[name] }
  },
  sendAssistantMessage: async () => {
    return {
      success: true,
      reply: 'Here is a fix.',
      proposal: {
        kind: 'edit',
        filename: `${proposalFor}.yaml`,
        yaml: 'graph:\n  nodes: []\n',
        base_hash: hashOf(files[proposalFor] ?? '')
      }
    }
  }
}))

async function setup() {
  vi.resetModules()
  for (const key of Object.keys(files)) delete files[key]
  files.wf = 'graph: {}\n'
  files.other = 'graph: {}\n'
  proposalFor = 'wf'
  const mod = await import('./useWorkflowAssistant.js')
  const api = mod.useWorkflowAssistant()
  api.vendor.value = 'anthropic'
  return api
}

async function proposeAndApply(api, workflow = 'wf') {
  api.setContext('workflow', workflow)
  proposalFor = workflow
  expect(await api.send('please fix')).toBe(true)
  const result = await api.applyProposal()
  expect(result.ok).toBe(true)
  return result
}

describe('useWorkflowAssistant rerun offer', () => {
  let api
  beforeEach(async () => {
    api = await setup()
  })

  it('offers a rerun after applying a proposal in a thread seeded from the Lab', async () => {
    api.setDraftSeed('fix these failures', { labJobId: 'job1', workflow: 'wf.yaml' })
    expect(api.labFixSource.value).toEqual({ labJobId: 'job1', workflow: 'wf' })
    await proposeAndApply(api)
    expect(api.rerunOffer.value).toEqual({ labJobId: 'job1', workflow: 'wf' })
    // The source is taken by the thread: it is not reused by another conversation.
    expect(api.labFixSource.value).toBeNull()
  })

  it('keeps the old one-argument setDraftSeed working, without an offer', async () => {
    api.setDraftSeed('plain text')
    expect(api.draftSeed.value).toBe('plain text')
    expect(api.labFixSource.value).toBeNull()
    await proposeAndApply(api)
    expect(api.rerunOffer.value).toBeNull()
  })

  it('gives no offer when the applied workflow is not the seeded one', async () => {
    api.setDraftSeed('fix', { labJobId: 'job1', workflow: 'wf' })
    await proposeAndApply(api, 'other')
    expect(api.rerunOffer.value).toBeNull()
  })

  it('clears the offer on Undo', async () => {
    api.setDraftSeed('fix', { labJobId: 'job1', workflow: 'wf' })
    await proposeAndApply(api)
    expect(api.rerunOffer.value).not.toBeNull()
    const undone = await api.undoLast('wf')
    expect(undone.ok).toBe(true)
    expect(api.rerunOffer.value).toBeNull()
  })

  it('clears the offer when another workflow is opened', async () => {
    api.setDraftSeed('fix', { labJobId: 'job1', workflow: 'wf' })
    await proposeAndApply(api)
    api.setContext('workflow', 'wf')
    expect(api.rerunOffer.value).not.toBeNull()
    api.setContext('workflow', 'other')
    expect(api.rerunOffer.value).toBeNull()
  })

  it('clears the offer on dismiss and on a new seed', async () => {
    api.setDraftSeed('fix', { labJobId: 'job1', workflow: 'wf' })
    await proposeAndApply(api)
    api.clearRerunOffer()
    expect(api.rerunOffer.value).toBeNull()
    api.setDraftSeed('fix', { labJobId: 'job2', workflow: 'wf' })
    await api.send('again')
    proposalFor = 'wf'
    expect((await api.applyProposal()).ok).toBe(true)
    expect(api.rerunOffer.value).toEqual({ labJobId: 'job2', workflow: 'wf' })
    api.setDraftSeed('unrelated text')
    expect(api.rerunOffer.value).toBeNull()
  })
})

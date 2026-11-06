// "Re-run failed scenarios" offer: set only after a Lab-seeded thread's proposal is applied to the
// same workflow; cleared by Undo or by moving to another workflow.
import { createHash } from 'node:crypto'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const hashOf = (text) => createHash('sha256').update(String(text).replace(/\r\n/g, '\n')).digest('hex')

const files = {}
let proposalFor = 'wf'
let savedSessions = []

vi.mock('@/utils/connectionModels.js', () => ({ modelsForConnection: async () => ({ models: [] }) }))
vi.mock('@/api/client.js', () => ({
  cancelAssistantRequest: async () => ({ success: true }),
  deleteAssistantSession: async () => ({ success: true }),
  fetchAssistantProviders: async () => ({ success: true, providers: [] }),
  fetchAssistantSession: async (id) => {
    const saved = savedSessions.find((s) => s.id === id)
    return saved ? { success: true, ...saved } : { success: false }
  },
  fetchAssistantSessions: async () => ({ success: true, sessions: savedSessions.map(({ id, title }) => ({ id, title })) }),
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
  savedSessions = []
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

  it('binds the Lab source to the thread shown when the panel took the seed', async () => {
    api.setContext('workflow', 'wf')
    expect(await api.send('an earlier question')).toBe(true)
    api.discardProposal()
    api.setDraftSeed('fix these failures', { labJobId: 'job1', workflow: 'wf' })
    expect(api.consumeDraftSeed()).toBe('fix these failures')
    expect(api.draftSeed.value).toBe('')
    // The user ignores the seed and starts another conversation, then applies an unrelated fix.
    api.newConversation()
    expect(api.labFixSource.value).toBeNull()
    await proposeAndApply(api)
    expect(api.rerunOffer.value).toBeNull()
  })

  it('the thread that took the seed takes the Lab source on its next message', async () => {
    api.setContext('workflow', 'wf')
    const first = api.currentThread.value
    api.setDraftSeed('fix', { labJobId: 'job1', workflow: 'wf' })
    api.consumeDraftSeed()
    expect(api.labFixSource.value).toMatchObject({ labJobId: 'job1', threadId: first.id })
    expect(await api.send('please fix')).toBe(true)
    expect(first.labSource).toMatchObject({ labJobId: 'job1', workflow: 'wf' })
    expect(api.labFixSource.value).toBeNull()
  })

  it('clears the offer and the source on a new conversation', async () => {
    api.setDraftSeed('fix', { labJobId: 'job1', workflow: 'wf' })
    await proposeAndApply(api)
    expect(api.rerunOffer.value).not.toBeNull()
    api.newConversation()
    expect(api.rerunOffer.value).toBeNull()
  })

  it('clears the offer and the source when a saved session is opened', async () => {
    api.setDraftSeed('fix', { labJobId: 'job1', workflow: 'wf' })
    await proposeAndApply(api)
    const id = api.currentThread.value.id
    api.setDraftSeed('fix again', { labJobId: 'job2', workflow: 'wf' })
    await proposeAndApplyAgain(api)
    expect(api.rerunOffer.value).not.toBeNull()
    api.setDraftSeed('pending', { labJobId: 'job3', workflow: 'wf' })
    expect((await api.openSession(id)).ok).toBe(true)
    expect(api.rerunOffer.value).toBeNull()
    expect(api.labFixSource.value).toBeNull()
  })

  it('blocks Undo while a rerun start is in flight', async () => {
    api.setDraftSeed('fix', { labJobId: 'job1', workflow: 'wf' })
    await proposeAndApply(api)
    api.setRerunStarting(true)
    expect(api.rerunStarting.value).toBe(true)
    const blocked = await api.undoLast('wf')
    expect(blocked).toEqual({ ok: false, reason: 'busy' })
    expect(files.wf).toBe('graph:\n  nodes: []\n')
    expect(api.canUndo.value).toBe(true)
    api.setRerunStarting(false)
    expect((await api.undoLast('wf')).ok).toBe(true)
  })
})

async function proposeAndApplyAgain(api) {
  expect(await api.send('again')).toBe(true)
  expect((await api.applyProposal()).ok).toBe(true)
}

describe('useWorkflowAssistant rerun offer: resumed session', () => {
  it('moves the Lab source to the saved session resumed in place of the empty thread', async () => {
    const api = await setup()
    savedSessions = [{ id: 'saved1', workflow: 'wf', title: 'old', messages: [] }]
    api.setDraftSeed('fix', { labJobId: 'job1', workflow: 'wf' })
    api.setContext('workflow', 'wf')
    api.consumeDraftSeed()
    await vi.waitFor(() => expect(api.currentThread.value.id).toBe('saved1'))
    expect(api.labFixSource.value).toMatchObject({ labJobId: 'job1', threadId: 'saved1' })
    await proposeAndApplyAgain(api)
    expect(api.rerunOffer.value).toEqual({ labJobId: 'job1', workflow: 'wf' })
  })
})

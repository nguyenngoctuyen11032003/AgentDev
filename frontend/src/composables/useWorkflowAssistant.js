/**
 * Chat state of the workflow assistant: one thread per context (new workflow / each workflow),
 * the selected model vendor, and applying / undoing the AI's proposals.
 *
 * State lives at module scope so closing and reopening the panel keeps the history. A page reload
 * clears it. Only the frontend writes workflow files, and only from `applyProposal`.
 */
import { computed, reactive, ref, watch } from 'vue'
import yaml from 'js-yaml'
import {
  cancelAssistantRequest,
  fetchAssistantProviders,
  fetchVueGraph,
  fetchYaml,
  mergeWorkflowDocument,
  postVuegraphs,
  postYaml,
  sendAssistantMessage,
  updateYaml
} from '@/api/client.js'
import { workflowKey } from '@/utils/workflowSync.js'
import { reconcileLayout } from '@/utils/layoutReconcile.js'

const VENDOR_STORAGE_KEY = 'agentdev:assistant-vendor'
const CREATE_KEY = 'create'

/** sha256 hex of a saved workflow text, line endings normalised (matches the backend base_hash). */
export async function workflowTextHash(text) {
  const normalised = String(text ?? '').replace(/\r\n/g, '\n')
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(normalised))
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

const readStoredVendor = () => {
  try {
    return localStorage.getItem(VENDOR_STORAGE_KEY) || ''
  } catch {
    return ''
  }
}

const storeVendor = (value) => {
  try {
    if (value) localStorage.setItem(VENDOR_STORAGE_KEY, value)
    else localStorage.removeItem(VENDOR_STORAGE_KEY)
  } catch {
    // storage unavailable (private mode): the choice lasts for this page only
  }
}

let idCounter = 0
const nextId = () => `m${Date.now().toString(36)}${(idCounter++).toString(36)}`

const newRequestId = () =>
  typeof crypto?.randomUUID === 'function'
    ? crypto.randomUUID()
    : `r${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`

const threadKey = (mode, workflow) => (mode === 'workflow' && workflow ? workflow : CREATE_KEY)

// `workflow` is the bare workflow name (no .yaml) the thread talks about; null for a new workflow.
const createThread = (workflow) => ({
  workflow,
  messages: [],
  pendingProposal: null,
  status: 'idle', // 'idle' | 'sending' | 'applying'
  requestId: null
})

// ---------------------------------------------------------------------------- module state

const context = ref({ mode: 'create', workflow: null })
const providers = ref([])
const vendor = ref(readStoredVendor())
const threads = reactive(new Map([[CREATE_KEY, createThread(null)]]))
// Last applied edit, kept for the Undo action: {workflow, oldYaml, oldLayout}
const lastApplied = ref(null)

watch(vendor, storeVendor)

const ensureThread = (key, workflow) => {
  if (!threads.has(key)) threads.set(key, createThread(workflow))
  return threads.get(key)
}

const currentThread = computed(() => {
  const { mode, workflow } = context.value
  return threads.get(threadKey(mode, workflow)) || threads.get(CREATE_KEY)
})

const canUndo = computed(() => !!lastApplied.value)

const systemNotice = (fields) => ({ id: nextId(), role: 'system', ...fields })

const findProposalMessage = (thread, proposal) =>
  proposal ? thread.messages.find((m) => m.proposal === proposal) : undefined

// ---------------------------------------------------------------------------- actions

function setContext(mode, workflow) {
  const name = mode === 'workflow' ? workflowKey(workflow) || null : null
  const nextMode = name ? 'workflow' : 'create'
  ensureThread(threadKey(nextMode, name), name)
  context.value = { mode: nextMode, workflow: name }
}

// Loads the signed-in providers and keeps `vendor` on an available one.
async function refreshProviders() {
  const result = await fetchAssistantProviders()
  if (result.success) {
    providers.value = Array.isArray(result.providers) ? result.providers : []
    const available = providers.value.filter((p) => p.available)
    if (!available.some((p) => p.vendor === vendor.value)) {
      vendor.value = available[0]?.vendor || ''
    }
  }
  return result
}

async function send(text) {
  const content = typeof text === 'string' ? text.trim() : ''
  const thread = currentThread.value
  if (!content || !vendor.value || thread.status !== 'idle') return false

  // Retrying after "quota exhausted": drop the notice and resend the same user message.
  const last = thread.messages[thread.messages.length - 1]
  const previous = thread.messages[thread.messages.length - 2]
  const isRetry =
    last?.role === 'system' && last.kind === 'quota' && last.retryText === content &&
    previous?.role === 'user' && previous.content === content
  if (isRetry) thread.messages.pop()
  else thread.messages.push({ id: nextId(), role: 'user', content })

  const requestId = newRequestId()
  const usedVendor = vendor.value
  thread.status = 'sending'
  thread.requestId = requestId

  const result = await sendAssistantMessage({
    vendor: usedVendor,
    workflow: thread.workflow ? `${thread.workflow}.yaml` : null,
    // System notices (errors, quota, conflicts) stay local.
    messages: thread.messages
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .map((m) => ({ role: m.role, content: m.content ?? '' })),
    pendingYaml: thread.pendingProposal?.yaml,
    requestId
  })

  // Stopped or reset while waiting: the late answer is dropped.
  if (thread.requestId !== requestId) return false
  thread.status = 'idle'
  thread.requestId = null

  if (result.success) {
    const message = {
      id: nextId(),
      role: 'assistant',
      content: typeof result.reply === 'string' ? result.reply : '',
      quickReplies: Array.isArray(result.quick_replies) ? result.quick_replies : []
    }
    if (Array.isArray(result.validation_errors) && result.validation_errors.length) {
      message.validationErrors = result.validation_errors
    }
    if (result.proposal) {
      for (const m of thread.messages) {
        if (m.proposal && !m.applied) m.superseded = true
      }
      message.proposal = result.proposal
    }
    thread.messages.push(message)
    if (result.proposal) thread.pendingProposal = message.proposal
    return true
  }

  if (result.error === 'cancelled') return false
  if (result.error === 'quota_exhausted') {
    thread.messages.push(systemNotice({ kind: 'quota', vendor: usedVendor, retryText: content, detail: result.detail }))
  } else {
    thread.messages.push(
      systemNotice({ kind: 'error', code: result.error || 'network', message: result.message, detail: result.detail })
    )
  }
  return false
}

// Drops the waiting state at once; the backend may not have registered the request yet, so its
// answer to the cancel call does not matter.
function stop() {
  const thread = currentThread.value
  const requestId = thread.requestId
  if (!requestId) return
  thread.requestId = null
  thread.status = 'idle'
  cancelAssistantRequest(requestId).catch(() => {})
}

function newConversation() {
  stop()
  const thread = currentThread.value
  thread.messages = []
  thread.pendingProposal = null
}

function discardProposal() {
  currentThread.value.pendingProposal = null
}

async function applyCreate(thread, proposal) {
  const result = await postYaml(proposal.filename, proposal.yaml)
  if (!result.success) return { ok: false, reason: 'failed', message: result.message }

  const message = findProposalMessage(thread, proposal)
  if (message) message.applied = true
  thread.pendingProposal = null

  // The conversation goes on in the new workflow's thread; "create" starts fresh.
  const name = workflowKey(proposal.filename)
  if (thread === threads.get(CREATE_KEY)) {
    thread.workflow = name
    threads.set(name, thread)
    threads.set(CREATE_KEY, createThread(null))
  }
  setContext('workflow', name)
  return { ok: true, filename: proposal.filename }
}

async function applyEdit(thread, proposal, formOpen) {
  const name = workflowKey(proposal.filename)
  const saved = await fetchYaml(name)
  if (!saved.success) return { ok: false, reason: 'failed', message: saved.message }

  const oldYaml = saved.content ?? ''
  if ((await workflowTextHash(oldYaml)) !== proposal.base_hash) {
    thread.messages.push(systemNotice({ kind: 'conflict', filename: proposal.filename }))
    return { ok: false, reason: 'conflict' }
  }
  if (formOpen) return { ok: false, reason: 'form_open' }

  let document
  try {
    document = yaml.load(proposal.yaml)
  } catch (error) {
    return { ok: false, reason: 'failed', message: error?.message }
  }

  const graphResult = await fetchVueGraph(name)
  const oldLayout = graphResult.success && typeof graphResult.content === 'string' ? graphResult.content : null

  const merged = await mergeWorkflowDocument(name, document)
  if (!merged.success) return { ok: false, reason: 'failed', message: merged.message }
  lastApplied.value = { workflow: name, oldYaml, oldLayout }

  let flow = null
  try {
    flow = oldLayout ? JSON.parse(oldLayout) : null
  } catch {
    flow = null
  }
  const nextLayout = reconcileLayout(flow, document?.graph || {}, proposal.diff_summary || {})
  if (nextLayout) {
    const saveLayout = await postVuegraphs({ filename: name, content: JSON.stringify(nextLayout) })
    if (!saveLayout.success) console.warn('Failed to save the reconciled layout:', saveLayout.message)
  }

  const message = findProposalMessage(thread, proposal)
  if (message) message.applied = true
  thread.pendingProposal = null
  return { ok: true, filename: proposal.filename }
}

/**
 * Writes the pending proposal. A proposal is always applicable, whatever its checks say.
 * @param {{formOpen: boolean}} options - formOpen: the node/edge form is open on the canvas.
 * @returns {Promise<{ok: boolean, reason?: 'conflict'|'form_open'|'failed', filename?: string, message?: string}>}
 */
async function applyProposal({ formOpen = false } = {}) {
  const thread = currentThread.value
  const proposal = thread.pendingProposal
  if (!proposal || thread.status !== 'idle') return { ok: false, reason: 'failed' }

  thread.status = 'applying'
  try {
    return proposal.kind === 'create'
      ? await applyCreate(thread, proposal)
      : await applyEdit(thread, proposal, formOpen)
  } catch (error) {
    console.error('Failed to apply the assistant proposal:', error)
    return { ok: false, reason: 'failed', message: error?.message }
  } finally {
    thread.status = 'idle'
  }
}

/** Restores the YAML text and layout saved before the last applied edit. */
async function undoLast() {
  const applied = lastApplied.value
  if (!applied) return { ok: false }

  const restored = await updateYaml(applied.workflow, applied.oldYaml)
  if (!restored.success) return { ok: false, message: restored.message }
  lastApplied.value = null

  if (applied.oldLayout) {
    const layout = await postVuegraphs({ filename: applied.workflow, content: applied.oldLayout })
    if (!layout.success) console.warn('Failed to restore the previous layout:', layout.message)
  }
  return { ok: true, filename: `${applied.workflow}.yaml` }
}

export function useWorkflowAssistant() {
  return {
    context,
    providers,
    vendor,
    threads,
    currentThread,
    canUndo,
    setContext,
    refreshProviders,
    send,
    stop,
    newConversation,
    applyProposal,
    discardProposal,
    undoLast
  }
}

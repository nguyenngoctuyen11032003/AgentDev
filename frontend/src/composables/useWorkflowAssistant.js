/**
 * Chat state of the workflow assistant: saved sessions per context (new workflow / each workflow),
 * the selected vendor and model, and applying / undoing the AI's proposals.
 *
 * Each conversation is a session saved on the server after every change, so a reload or another
 * day continues it with its context. Opening a workflow resumes its latest session; "New
 * conversation" starts another one and the history list switches between them. Only the frontend
 * writes workflow files, and only from `applyProposal`.
 */
import { computed, reactive, ref, watch } from 'vue'
import yaml from 'js-yaml'
import {
  cancelAssistantRequest,
  deleteAssistantSession,
  fetchAssistantProviders,
  fetchAssistantSession,
  fetchAssistantSessions,
  fetchVueGraph,
  fetchYaml,
  mergeWorkflowDocument,
  postVuegraphs,
  postYaml,
  saveAssistantSession,
  sendAssistantMessage,
  updateYaml
} from '@/api/client.js'
import { workflowKey } from '@/utils/workflowSync.js'
import { reconcileLayout } from '@/utils/layoutReconcile.js'
import { sha256Hex } from '@/utils/sha256.js'
import { modelsForConnection } from '@/utils/connectionModels.js'

const VENDOR_STORAGE_KEY = 'agentdev:assistant-vendor'
const MODEL_STORAGE_KEY = 'agentdev:assistant-models'
// ":" cannot appear in a workflow name, so no workflow context can take this key.
const CREATE_KEY = ':create'
// What is sent per turn. The backend keeps the first user message and the last 24 in full and
// adds a one-line recap of each older one, so the request carries more than that, within the
// route's limits (200 messages, 400k characters).
const HISTORY_LIMIT = 160
const HISTORY_CHAR_BUDGET = 300_000
const SAVE_DELAY_MS = 400
const TITLE_LENGTH = 80

/** sha256 hex of a saved workflow text, line endings normalised (matches the backend base_hash). */
export async function workflowTextHash(text) {
  const normalised = String(text ?? '').replace(/\r\n/g, '\n')
  const bytes = new TextEncoder().encode(normalised)
  // crypto.subtle exists only in secure contexts (https, localhost); over http on a LAN address
  // it is undefined, so fall back to the plain JS digest (same hex).
  if (typeof globalThis.crypto?.subtle?.digest !== 'function') return sha256Hex(bytes)
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes)
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

/**
 * The newest messages within HISTORY_LIMIT and the character budget, plus the first user message
 * (the original request) when it fell out.
 */
export function trimHistory(messages) {
  const kept = []
  let chars = 0
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const size = messages[i].content.length
    if (kept.length >= HISTORY_LIMIT || (kept.length && chars + size > HISTORY_CHAR_BUDGET)) break
    kept.unshift(messages[i])
    chars += size
  }
  const first = messages.find((m) => m.role === 'user')
  if (first && !kept.includes(first) && chars + first.content.length <= HISTORY_CHAR_BUDGET + 50_000) {
    kept.unshift(first)
  }
  return kept
}

// What became of a proposal card, told to the model on later turns: it only sees the reply text
// otherwise, and would not know whether the user applied, discarded or never used the card.
function proposalNote(m, pending) {
  const label = `[Proposal v${m.proposalNumber || 1} for ${m.proposal.filename}:`
  if (m.applied) return `${label} the user applied it; the saved file now includes it.]`
  if (m.conflicted) return `${label} not applied, the file was changed elsewhere first.]`
  if (m.proposal === pending) return `${label} shown to the user, not applied yet.]`
  if (m.superseded) return `${label} replaced by a later proposal.]`
  return `${label} the user discarded it.]`
}

/**
 * Messages sent to the model: user and assistant turns only (local notices stay local), the fate
 * of each proposal card added to its reply, and back-to-back messages of one role merged (a message
 * sent after an error has no reply in between; some providers reject two user turns in a row).
 */
export function chatHistory(thread) {
  const out = []
  for (const m of thread.messages) {
    if (m.role !== 'user' && m.role !== 'assistant') continue
    let content = m.content ?? ''
    if (m.role === 'assistant') {
      if (m.proposal) content = `${content}\n\n${proposalNote(m, thread.pendingProposal)}`.trim()
      else if (m.validationErrors?.length) content = `${content}\n\n[Your proposal failed validation and was not shown.]`.trim()
      if (!content) continue
    }
    const last = out[out.length - 1]
    if (last && last.role === m.role) last.content = `${last.content}\n\n${content}`
    else out.push({ role: m.role, content })
  }
  // A history may not start with a reply only (e.g. its first question was trimmed away).
  while (out.length && out[0].role !== 'user') out.shift()
  return trimHistory(out)
}

const readStored = (key, fallback) => {
  try {
    return localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}

const writeStored = (key, value) => {
  try {
    if (value) localStorage.setItem(key, value)
    else localStorage.removeItem(key)
  } catch {
    // storage unavailable (private mode): the choice lasts for this page only
  }
}

const readStoredModels = () => {
  try {
    const value = JSON.parse(readStored(MODEL_STORAGE_KEY, '{}'))
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
  } catch {
    return {}
  }
}

let idCounter = 0
const nextId = () => `m${Date.now().toString(36)}${(idCounter++).toString(36)}`

const randomId = () =>
  typeof crypto?.randomUUID === 'function'
    ? crypto.randomUUID().replace(/-/g, '')
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 14)}`

const threadKey = (mode, workflow) => (mode === 'workflow' && workflow ? workflow : CREATE_KEY)
const keyOfWorkflow = (workflow) => threadKey(workflow ? 'workflow' : 'create', workflow)

// `workflow` is the bare workflow name (no .yaml) the thread talks about; null for a new workflow.
// `id` is the saved session's id; `saved` turns true once the server has it.
const createThread = (workflow, id = `s${randomId()}`) => ({
  id,
  workflow,
  title: '',
  updatedAt: null,
  saved: false,
  messages: [],
  pendingProposal: null,
  status: 'idle', // 'idle' | 'sending' | 'applying'
  requestId: null,
  sendingSince: null,
  // A proposal was applied after the last user message: quick replies stay hidden until the user
  // writes again (they were offered before the apply and no longer fit).
  appliedSinceUserMessage: false
})

// ---------------------------------------------------------------------------- module state

const context = ref({ mode: 'create', workflow: null })
const providers = ref([])
const vendor = ref(readStored(VENDOR_STORAGE_KEY, ''))
// Chosen model per vendor ('' = the account's default model).
const modelByVendor = reactive(readStoredModels())
const models = ref([]) // models of the selected vendor's account: [{id, name, primary}]
const modelsLoading = ref(false)
// Every session opened in this page, by id.
const threads = reactive(new Map())
// Context key -> id of the session shown for it.
const activeByContext = reactive(new Map())
// Context key -> {items: [summary], loading, loaded}
const sessionLists = reactive(new Map())
// Last applied edit, kept for the Undo action:
// {workflow, oldYaml, oldLayout, appliedHash, thread, message, proposal}
const lastApplied = ref(null)
// Text another page (Lab) wants in the composer, ready to edit and send; the panel takes it once.
const draftSeed = ref('')
const setDraftSeed = (text) => {
  draftSeed.value = String(text || '')
}

watch(vendor, (value) => writeStored(VENDOR_STORAGE_KEY, value))

const model = computed({
  get: () => (vendor.value && modelByVendor[vendor.value]) || '',
  set: (value) => {
    if (!vendor.value) return
    modelByVendor[vendor.value] = value || ''
    writeStored(MODEL_STORAGE_KEY, JSON.stringify({ ...modelByVendor }))
  }
})

// The model list of the selected vendor's signed-in account (cached a minute by connectionModels).
let modelsToken = 0
async function refreshModels() {
  const provider = providers.value.find((p) => p.vendor === vendor.value && p.available)
  const token = ++modelsToken
  if (!provider?.connection_id) {
    models.value = []
    return
  }
  modelsLoading.value = true
  try {
    const result = await modelsForConnection(provider.connection_id)
    if (token !== modelsToken) return
    models.value = Array.isArray(result.models) ? result.models : []
    // A remembered model the account no longer offers falls back to the default.
    if (model.value && models.value.length && !models.value.some((m) => m.id === model.value)) model.value = ''
  } catch {
    if (token === modelsToken) models.value = []
  } finally {
    if (token === modelsToken) modelsLoading.value = false
  }
}
watch(vendor, () => refreshModels())

const contextKey = () => threadKey(context.value.mode, context.value.workflow)

const newThreadFor = (key, workflow) => {
  const thread = createThread(workflow)
  threads.set(thread.id, thread)
  activeByContext.set(key, thread.id)
  return threads.get(thread.id)
}

const ensureActive = (key, workflow) => {
  const id = activeByContext.get(key)
  return (id && threads.get(id)) || newThreadFor(key, workflow)
}

ensureActive(CREATE_KEY, null)

const currentThread = computed(() => {
  const id = activeByContext.get(contextKey())
  return (id && threads.get(id)) || threads.get(activeByContext.get(CREATE_KEY))
})

const currentSessions = computed(() => sessionLists.get(contextKey())?.items || [])
const sessionsLoading = computed(() => !!sessionLists.get(contextKey())?.loading)

const canUndo = computed(() => !!lastApplied.value)
// Id of the chat message whose proposal Undo would revert (its card offers Undo too).
const undoMessageId = computed(() => lastApplied.value?.message?.id ?? null)

const systemNotice = (fields) => ({ id: nextId(), role: 'system', ...fields })

const ASSISTANT_INTENTS = ['ask', 'explain', 'propose']

const findProposalMessage = (thread, proposal) =>
  proposal ? thread.messages.find((m) => m.proposal === proposal) : undefined

// ---------------------------------------------------------------------------- saving sessions

const titleOf = (thread) => {
  if (thread.title) return thread.title
  const first = thread.messages.find((m) => m.role === 'user')?.content || ''
  const flat = first.replace(/\s+/g, ' ').trim()
  return flat.length > TITLE_LENGTH ? `${flat.slice(0, TITLE_LENGTH - 1).trimEnd()}…` : flat
}

const countTurns = (messages) => messages.filter((m) => m.role === 'user' || m.role === 'assistant').length

const upsertSummary = (key, summary) => {
  const list = sessionLists.get(key)
  if (!list) return
  list.items = [summary, ...list.items.filter((s) => s.id !== summary.id)]
}

const removeSummary = (id) => {
  for (const list of sessionLists.values()) list.items = list.items.filter((s) => s.id !== id)
}

const saveTimers = new Map()

async function saveNow(thread) {
  saveTimers.delete(thread.id)
  // Deleted meanwhile, or nothing worth keeping yet.
  if (!threads.has(thread.id) || !thread.messages.some((m) => m.role === 'user')) return
  const pending = thread.pendingProposal ? findProposalMessage(thread, thread.pendingProposal) : null
  const title = titleOf(thread)
  const result = await saveAssistantSession(thread.id, {
    workflow: thread.workflow,
    title,
    messages: thread.messages.map((m) => ({ ...m })),
    pending_message_id: pending?.id || null,
    vendor: vendor.value || null,
    model: model.value || null
  })
  if (!result.success) {
    console.warn('Could not save the assistant conversation:', result.message)
    return
  }
  if (!threads.has(thread.id)) {
    // Deleted while the save was on its way: remove what the save wrote back.
    deleteAssistantSession(thread.id).catch(() => {})
    return
  }
  thread.saved = true
  thread.title = title
  thread.updatedAt = result.updated_at ?? Date.now() / 1000
  // A session that moved (to a workflow it created) leaves the other lists.
  removeSummary(thread.id)
  upsertSummary(keyOfWorkflow(thread.workflow), {
    id: thread.id,
    workflow: thread.workflow,
    title,
    updated_at: thread.updatedAt,
    message_count: countTurns(thread.messages)
  })
}

// Saves shortly after the last change (several changes in a row make one request).
function persist(thread) {
  if (!thread) return
  clearTimeout(saveTimers.get(thread.id))
  saveTimers.set(thread.id, setTimeout(() => saveNow(thread), SAVE_DELAY_MS))
}

/** Loads the saved sessions of a context (default: the current one). */
async function loadSessions(key = contextKey()) {
  if (!sessionLists.has(key)) sessionLists.set(key, { items: [], loading: false, loaded: false })
  const entry = sessionLists.get(key)
  entry.loading = true
  const result = await fetchAssistantSessions(key === CREATE_KEY ? null : key)
  entry.loading = false
  if (result.success && Array.isArray(result.sessions)) {
    entry.items = result.sessions
    entry.loaded = true
  }
  return entry
}

// A thread from a saved session. A request that was running when the page closed never got its
// answer: the session then ends with a "stopped" notice that offers to send the question again.
function threadFromSession(data) {
  const thread = createThread(data.workflow || null, data.id)
  thread.title = data.title || ''
  thread.updatedAt = data.updated_at ?? null
  thread.saved = true
  thread.messages = Array.isArray(data.messages)
    ? data.messages.filter((m) => m && typeof m === 'object' && typeof m.id === 'string')
    : []
  const pending = data.pending_message_id && thread.messages.find((m) => m.id === data.pending_message_id)
  thread.pendingProposal = pending?.proposal && !pending.applied ? pending.proposal : null
  const last = thread.messages[thread.messages.length - 1]
  if (last?.role === 'user') {
    thread.messages.push(systemNotice({ kind: 'stopped', vendor: data.vendor || '', retryText: last.content }))
  }
  return thread
}

/** Shows a saved session (picked in the history list). */
async function openSession(id) {
  const known = threads.get(id)
  if (known) {
    activeByContext.set(keyOfWorkflow(known.workflow), id)
    return { ok: true }
  }
  const result = await fetchAssistantSession(id)
  if (!result.success) return { ok: false, message: result.message }
  if (!threads.has(id)) threads.set(id, threadFromSession(result))
  const thread = threads.get(id)
  // Opened where it belongs, even if the user moved to another workflow while it loaded.
  activeByContext.set(keyOfWorkflow(thread.workflow), thread.id)
  return { ok: true }
}

/** Deletes a saved session; when it is on screen, a new empty conversation replaces it. */
async function deleteSession(id) {
  const thread = threads.get(id)
  if (thread?.requestId) stopThread(thread, false)
  clearTimeout(saveTimers.get(id))
  saveTimers.delete(id)
  const result = await deleteAssistantSession(id)
  if (!result.success && result.status !== 404) return { ok: false, message: result.message }
  removeSummary(id)
  threads.delete(id)
  if (lastApplied.value?.thread?.id === id) lastApplied.value = null
  for (const [key, active] of [...activeByContext.entries()]) {
    if (active === id) newThreadFor(key, key === CREATE_KEY ? null : key)
  }
  return { ok: true }
}

// ---------------------------------------------------------------------------- actions

// Opening a context for the first time in this page resumes its latest saved session.
function setContext(mode, workflow) {
  const name = mode === 'workflow' ? workflowKey(workflow) || null : null
  const nextMode = name ? 'workflow' : 'create'
  const key = threadKey(nextMode, name)
  const firstVisit = !activeByContext.has(key)
  const shown = ensureActive(key, name)
  context.value = { mode: nextMode, workflow: name }
  loadSessions(key).then(async (list) => {
    if (!firstVisit || !list.items.length) return
    // Only while untouched: the user has not started a new conversation there meanwhile.
    if (activeByContext.get(key) !== shown.id || shown.messages.length || shown.status !== 'idle') return
    const opened = await openSession(list.items[0].id)
    if (opened.ok && activeByContext.get(key) !== shown.id && !shown.messages.length) threads.delete(shown.id)
  })
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
    refreshModels()
  }
  return result
}

async function send(text) {
  const content = typeof text === 'string' ? text.trim() : ''
  const thread = currentThread.value
  if (!content || !vendor.value || thread.status !== 'idle') return false

  // Retrying after "quota exhausted" or Stop: drop the notice and resend the same user message.
  const last = thread.messages[thread.messages.length - 1]
  const previous = thread.messages[thread.messages.length - 2]
  const isRetry =
    last?.role === 'system' && (last.kind === 'quota' || last.kind === 'stopped') && last.retryText === content &&
    previous?.role === 'user' && previous.content === content
  if (isRetry) thread.messages.pop()
  else thread.messages.push({ id: nextId(), role: 'user', content, at: Date.now() })
  thread.appliedSinceUserMessage = false

  const requestId = randomId()
  const usedVendor = vendor.value
  const usedModel = model.value
  thread.status = 'sending'
  thread.requestId = requestId
  thread.sendingSince = Date.now()
  // Saved before the answer, so a reload during a long turn keeps the question.
  persist(thread)

  const result = await sendAssistantMessage({
    vendor: usedVendor,
    model: usedModel,
    workflow: thread.workflow ? `${thread.workflow}.yaml` : null,
    messages: chatHistory(thread),
    pendingYaml: thread.pendingProposal?.yaml,
    requestId
  })

  // Stopped or deleted while waiting: the late answer is dropped.
  if (thread.requestId !== requestId) return false
  thread.status = 'idle'
  thread.requestId = null
  thread.sendingSince = null

  if (result.success) {
    const message = {
      id: nextId(),
      role: 'assistant',
      content: typeof result.reply === 'string' ? result.reply : '',
      quickReplies: Array.isArray(result.quick_replies) ? result.quick_replies : [],
      vendor: usedVendor,
      at: Date.now()
    }
    const usedName = typeof result.model_used === 'string' && result.model_used ? result.model_used : usedModel
    if (usedName) message.model = usedName
    if (Array.isArray(result.validation_errors) && result.validation_errors.length) {
      message.validationErrors = result.validation_errors
    }
    // Optional fields (older backends omit them): what the turn was for, and the token usage.
    if (ASSISTANT_INTENTS.includes(result.intent)) message.intent = result.intent
    if (result.usage && typeof result.usage === 'object') message.usage = result.usage
    if (result.proposal) {
      let count = 0
      for (const m of thread.messages) {
        if (!m.proposal) continue
        count += 1
        if (!m.applied) m.superseded = true
      }
      message.proposal = result.proposal
      // "Version N" of this thread, so the user can tell the cards apart.
      message.proposalNumber = count + 1
    }
    thread.messages.push(message)
    if (result.proposal) thread.pendingProposal = message.proposal
    persist(thread)
    return true
  }

  if (result.error === 'cancelled') {
    persist(thread)
    return false
  }
  if (result.error === 'quota_exhausted') {
    thread.messages.push(systemNotice({ kind: 'quota', vendor: usedVendor, retryText: content, detail: result.detail }))
  } else {
    thread.messages.push(
      systemNotice({ kind: 'error', code: result.error || 'network', message: result.message, detail: result.detail })
    )
  }
  persist(thread)
  return false
}

// Drops the waiting state at once; the backend may not have registered the request yet, so its
// answer to the cancel call does not matter. A neutral "Stopped." notice offers to resend the
// last user message; send() ignores the late answer (the thread's requestId no longer matches).
function stopThread(thread, notice = true) {
  const requestId = thread.requestId
  if (!requestId) return
  thread.requestId = null
  thread.status = 'idle'
  thread.sendingSince = null
  cancelAssistantRequest(requestId).catch(() => {})
  const lastUser = [...thread.messages].reverse().find((m) => m.role === 'user')
  if (notice && lastUser) {
    thread.messages.push(systemNotice({ kind: 'stopped', vendor: vendor.value, retryText: lastUser.content }))
    persist(thread)
  }
}

function stop() {
  stopThread(currentThread.value)
}

// Starts another conversation in the same context. The current one stays in the history; a reply
// still on its way lands there and is saved.
function newConversation() {
  const thread = currentThread.value
  if (!thread.messages.length && thread.status === 'idle') return
  newThreadFor(contextKey(), context.value.workflow)
}

function discardProposal() {
  const thread = currentThread.value
  thread.pendingProposal = null
  persist(thread)
}

async function applyCreate(thread, proposal) {
  const result = await postYaml(proposal.filename, proposal.yaml)
  if (!result.success) return { ok: false, reason: 'failed', message: result.message }

  const message = findProposalMessage(thread, proposal)
  if (message) message.applied = true
  thread.pendingProposal = null
  thread.appliedSinceUserMessage = true

  // The conversation goes on as the new workflow's session; "new workflow" starts fresh.
  const name = workflowKey(proposal.filename)
  if (!thread.workflow) {
    thread.workflow = name
    activeByContext.set(threadKey('workflow', name), thread.id)
    if (activeByContext.get(CREATE_KEY) === thread.id) newThreadFor(CREATE_KEY, null)
  }
  persist(thread)
  setContext('workflow', name)
  return { ok: true, filename: proposal.filename }
}

async function applyEdit(thread, proposal, formOpen) {
  const name = workflowKey(proposal.filename)
  const saved = await fetchYaml(name)
  if (!saved.success) return { ok: false, reason: 'failed', message: saved.message }

  const oldYaml = saved.content ?? ''
  if ((await workflowTextHash(oldYaml)) !== proposal.base_hash) {
    // The proposal was built on an older file. Drop it: a redo must start from the current file,
    // never resend this one as pending_yaml (applying it would revert the other edit).
    const stale = findProposalMessage(thread, proposal)
    if (stale) stale.conflicted = true
    thread.pendingProposal = null
    thread.messages.push(systemNotice({ kind: 'conflict', filename: proposal.filename }))
    persist(thread)
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

  // The YAML is written: from here on the apply has succeeded, whatever happens to the layout.
  const message = findProposalMessage(thread, proposal)
  if (message) message.applied = true
  thread.pendingProposal = null
  thread.appliedSinceUserMessage = true
  persist(thread)
  lastApplied.value = { workflow: name, oldYaml, oldLayout, appliedHash: null, thread, message, proposal }
  // Read back through the ref: the reactive proxy, so canUndo / undoMessageId stay in sync.
  const applied = lastApplied.value

  let layoutSaved = true
  try {
    // Hash of what was written, so Undo can tell whether the file changed again since.
    let appliedText = typeof merged.content === 'string' ? merged.content : null
    if (appliedText === null) {
      const reread = await fetchYaml(name)
      appliedText = reread.success ? reread.content ?? '' : null
    }
    if (appliedText !== null) applied.appliedHash = await workflowTextHash(appliedText)

    let flow = null
    try {
      flow = oldLayout ? JSON.parse(oldLayout) : null
    } catch {
      flow = null
    }
    const nextLayout = reconcileLayout(flow, document?.graph || {}, proposal.diff_summary || {})
    if (nextLayout) {
      const saveLayout = await postVuegraphs({ filename: name, content: JSON.stringify(nextLayout) })
      if (!saveLayout.success) {
        layoutSaved = false
        console.warn('Failed to save the reconciled layout:', saveLayout.message)
      }
    }
  } catch (error) {
    layoutSaved = false
    console.warn('The workflow was saved, but updating its layout failed:', error)
  }
  return layoutSaved
    ? { ok: true, filename: proposal.filename }
    : { ok: true, filename: proposal.filename, warning: 'layout' }
}

/**
 * Writes the pending proposal. A proposal is always applicable, whatever its checks say.
 * @param {{formOpen: boolean}} options - formOpen: the node/edge form is open on the canvas.
 * reason 'busy': another apply or a reply is running (e.g. a double click); 'none': nothing is
 * pending. Neither needs a message. warning 'layout': the workflow was saved but its canvas
 * layout could not be updated.
 * @returns {Promise<{ok: boolean, reason?: 'busy'|'none'|'conflict'|'form_open'|'failed', warning?: 'layout', filename?: string, message?: string}>}
 */
async function applyProposal({ formOpen = false } = {}) {
  const thread = currentThread.value
  const proposal = thread.pendingProposal
  if (!proposal) return { ok: false, reason: 'none' }
  if (thread.status !== 'idle') return { ok: false, reason: 'busy' }

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

/**
 * Restores the YAML text and layout saved before the last applied edit. Refuses (reason 'stale')
 * without writing when the file changed after the apply, so later edits are never wiped.
 * @param {string} [workflow] - the workflow the Undo button belongs to; when the last apply wrote
 *   another workflow, nothing is undone (reason 'none').
 * @returns {Promise<{ok: boolean, reason?: 'none'|'stale'|'failed', filename?: string, message?: string}>}
 */
async function undoLast(workflow) {
  const applied = lastApplied.value
  if (!applied) return { ok: false, reason: 'none' }
  if (workflow && workflowKey(workflow) !== applied.workflow) return { ok: false, reason: 'none' }

  const current = await fetchYaml(applied.workflow)
  if (!current.success) return { ok: false, reason: 'failed', message: current.message }
  if (!applied.appliedHash || (await workflowTextHash(current.content ?? '')) !== applied.appliedHash) {
    lastApplied.value = null
    return { ok: false, reason: 'stale' }
  }

  // oldYaml came from /get, which reads in text mode: a CRLF file is restored with LF line endings.
  const restored = await updateYaml(applied.workflow, applied.oldYaml)
  if (!restored.success) return { ok: false, reason: 'failed', message: restored.message }
  lastApplied.value = null
  reopenProposal(applied)

  if (applied.oldLayout) {
    const layout = await postVuegraphs({ filename: applied.workflow, content: applied.oldLayout })
    if (!layout.success) console.warn('Failed to restore the previous layout:', layout.message)
  }
  return { ok: true, filename: `${applied.workflow}.yaml` }
}

// After an Undo the proposal is no longer applied. It becomes pending again (its base_hash matches
// the restored file), unless a newer proposal has come since.
function reopenProposal({ thread, message, proposal }) {
  if (!message) return
  message.applied = false
  const index = thread.messages.indexOf(message)
  if (index === -1) return
  const newer = thread.messages.slice(index + 1).some((m) => m.proposal)
  if (newer || thread.pendingProposal) message.superseded = true
  else thread.pendingProposal = proposal
  persist(thread)
}

export function useWorkflowAssistant() {
  return {
    context,
    providers,
    vendor,
    model,
    models,
    modelsLoading,
    refreshModels,
    threads,
    currentThread,
    currentSessions,
    sessionsLoading,
    loadSessions,
    openSession,
    deleteSession,
    canUndo,
    undoMessageId,
    setContext,
    refreshProviders,
    send,
    stop,
    newConversation,
    applyProposal,
    discardProposal,
    undoLast,
    draftSeed,
    setDraftSeed
  }
}

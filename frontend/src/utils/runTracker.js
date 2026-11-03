// What happened in the current run, per workflow step: the Kanban board and the
// dashboard both read from here. It is fed by the same WebSocket events that drive the
// chat and the office (node start/end, model and tool calls, handoffs, human input),
// including the replay of a saved session, so reopening a run rebuilds the board.
import { reactive } from 'vue'

const MAX_EVENTS = 300
const TECHNICAL_SUMMARY = /^Workflow (finished|completed) with \d+/i
const OUTPUT_PREVIEW = 600

// Backend log timestamps are ISO strings in local time; fall back to "now" for live UI events.
const toMs = (at) => {
  if (typeof at === 'number' && Number.isFinite(at)) return at
  const parsed = at ? Date.parse(at) : NaN
  return Number.isFinite(parsed) ? parsed : Date.now()
}

const preview = (text) => {
  const value = typeof text === 'string' ? text : text == null ? '' : JSON.stringify(text)
  const clean = value.replace(/\s+\n/g, '\n').trim()
  return clean.length > OUTPUT_PREVIEW ? `${clean.slice(0, OUTPUT_PREVIEW - 1)}…` : clean
}

export function createRunTracker() {
  const state = reactive({
    startedAt: null,
    endedAt: null,
    outcome: '', // '' while running | 'completed' | 'cancelled' | 'error'
    task: null, // { text, attachments, at }
    summary: '',
    error: '',
    tokenUsage: null,
    nodes: {}, // node id -> { runs: [...], waiting, lastAt }
    events: [], // newest last: { id, at, kind, nodeId, target, text }
    inputs: 0
  })
  let seq = 0

  const nodeOf = (id) => {
    if (!state.nodes[id]) state.nodes[id] = { runs: [], waiting: false, lastAt: null, pendingTask: '' }
    return state.nodes[id]
  }

  const openRun = (node) => {
    const run = node.runs[node.runs.length - 1]
    return run && !run.endedAt ? run : null
  }

  const pushEvent = (kind, nodeId, at, extra = {}) => {
    state.events.push({ id: ++seq, at, kind, nodeId, ...extra })
    if (state.events.length > MAX_EVENTS) state.events.splice(0, state.events.length - MAX_EVENTS)
  }

  // Replayed messages without a timestamp arrive "now"; the earliest real time wins
  const touchRun = (at) => {
    if (!state.startedAt || at < state.startedAt) state.startedAt = at
  }

  // Only backend events carry real times (your own messages are replayed untimed)
  const TIMED = new Set(['start', 'end', 'tool', 'handoff'])
  const lastEventAt = () =>
    state.events.reduce((max, event) => (TIMED.has(event.kind) ? Math.max(max, event.at) : max), 0)

  // `delegatedBy`: the lead that handed this task over (team workflows), '' otherwise
  const nodeStart = (id, at, { delegatedBy = '' } = {}) => {
    if (!id) return
    const time = toMs(at)
    touchRun(time)
    const node = nodeOf(id)
    if (openRun(node)) return
    node.waiting = false
    node.lastAt = time
    const task = node.pendingTask || ''
    node.pendingTask = ''
    node.runs.push({
      index: node.runs.length + 1,
      task, // what the lead asked for (team workflows)
      startedAt: time,
      endedAt: null,
      status: 'working',
      delegatedBy,
      activity: null, // { kind: 'model' | 'tool', name }
      models: 0,
      tools: [],
      output: ''
    })
    pushEvent('start', id, time, delegatedBy ? { target: delegatedBy } : {})
  }

  const activity = (id, kind, name, active, at) => {
    if (!id) return
    const time = toMs(at)
    let run = openRun(nodeOf(id))
    if (!run) {
      nodeStart(id, time)
      run = openRun(nodeOf(id))
    }
    nodeOf(id).lastAt = time
    if (active) {
      run.activity = { kind, name: name || '' }
      if (kind === 'model') run.models += 1
      else run.tools.push(name || '?')
      if (kind === 'tool') pushEvent('tool', id, time, { text: name || '' })
    } else if (run.activity?.kind === kind) {
      run.activity = null
    }
  }

  const nodeEnd = (id, output, at) => {
    if (!id) return
    const time = toMs(at)
    const node = nodeOf(id)
    let run = openRun(node)
    if (!run) {
      // The start was not seen (e.g. a partial replay): record a zero-length run
      nodeStart(id, time)
      run = openRun(node)
    }
    run.endedAt = time
    run.status = 'done'
    run.activity = null
    run.output = preview(output)
    node.waiting = false
    node.lastAt = time
    pushEvent('end', id, time, { text: run.output.split('\n')[0].slice(0, 140) })
  }

  const waitingInput = (id, at) => {
    const time = toMs(at)
    if (id) {
      const node = nodeOf(id)
      node.waiting = true
      node.lastAt = time
    }
    pushEvent('waiting', id || '', time)
  }

  const inputSent = (text, at) => {
    const time = toMs(at)
    state.inputs += 1
    for (const node of Object.values(state.nodes)) node.waiting = false
    pushEvent('input', '', time, { text: preview(text).slice(0, 140) })
  }

  // A lead's delegate call names the member and the task just before the member starts
  const assign = (memberId, task) => {
    if (!memberId || !task) return
    nodeOf(memberId).pendingTask = preview(task)
  }

  const handoff = (from, to, at) => {
    const time = toMs(at)
    pushEvent('handoff', from, time, { target: to })
  }

  const begin = (text, attachments = [], at) => {
    const time = toMs(at)
    // A new task in a finished session starts a fresh board
    if (state.outcome) reset()
    if (!state.startedAt) state.startedAt = time
    state.task = { text: preview(text), attachments: [...attachments], at: time }
    pushEvent('task', '', time, { text: preview(text).slice(0, 140) })
  }

  const lastLeadOutput = () => {
    let best = null
    for (const node of Object.values(state.nodes)) {
      for (const run of node.runs) {
        if (run.delegatedBy || !run.endedAt || !run.output) continue
        if (!best || run.endedAt >= best.endedAt) best = run
      }
    }
    return best?.output || ''
  }

  const finish = (outcome,{ summary = '', error = '', tokenUsage = null, at } = {}) => {
    // Completion messages carry no time: while a step is still open it is "now" (live
    // stop); otherwise the run ended with its last event (also right for replays).
    const stillOpen = Object.values(state.nodes).some((node) => openRun(node))
    const time = at ? toMs(at) : stillOpen ? Date.now() : lastEventAt() || Date.now()
    state.outcome = outcome
    state.endedAt = time
    // The backend's own summary ("Workflow finished with N node outputs ...") says nothing
    // to a person: the result is then what the lead (a step nobody delegated) said last.
    const useful = summary && !TECHNICAL_SUMMARY.test(summary) ? summary : ''
    state.summary = preview(useful || (outcome === 'completed' ? lastLeadOutput() : ''))
    state.error = preview(error)
    if (tokenUsage) state.tokenUsage = tokenUsage
    for (const node of Object.values(state.nodes)) {
      node.waiting = false
      const run = openRun(node)
      if (run) {
        run.endedAt = time
        run.status = outcome === 'completed' ? 'done' : outcome
        run.activity = null
      }
    }
    pushEvent(outcome, '', time, { text: state.summary.split('\n')[0].slice(0, 140) || state.error.slice(0, 140) })
  }

  const reset = () => {
    state.startedAt = null
    state.endedAt = null
    state.outcome = ''
    state.task = null
    state.summary = ''
    state.error = ''
    state.tokenUsage = null
    state.nodes = {}
    state.events = []
    state.inputs = 0
  }

  return { state, begin, nodeStart, activity, nodeEnd, waitingInput, inputSent, assign, handoff, finish, reset }
}

// ---------------------------------------------------------------- derived views

/** Status of one workflow step: 'working' | 'waiting' | 'done' | 'error' | 'cancelled' | 'todo'. */
export function stepStatus(node) {
  if (!node || !node.runs.length) return node?.waiting ? 'waiting' : 'todo'
  if (node.waiting) return 'waiting'
  const last = node.runs[node.runs.length - 1]
  return last.endedAt ? last.status : 'working'
}

export function stepDuration(node, now = Date.now()) {
  if (!node) return 0
  return node.runs.reduce((sum, run) => sum + ((run.endedAt || now) - run.startedAt), 0)
}

/**
 * Totals of the backend token report (TokenTracker.get_token_usage): tokens, and the cost
 * the Claude CLI reports per call (metadata.total_cost_usd), overall and per step.
 */
export function usageTotals(usage) {
  const pick = (value) => (Number.isFinite(value) ? value : 0)
  const total = usage?.total_usage || usage?.total || usage?.totals || usage || {}
  const byNode = {}
  let cost = 0
  let priced = false
  for (const call of Array.isArray(usage?.call_history) ? usage.call_history : []) {
    const price = Number(call?.metadata?.total_cost_usd)
    if (!Number.isFinite(price)) continue
    priced = true
    cost += price
    const id = call.node_id || ''
    byNode[id] = (byNode[id] || 0) + price
  }
  const nodes = {}
  for (const [id, item] of Object.entries(usage?.node_usages || {})) {
    nodes[id] = { tokens: pick(item?.total_tokens), cost: byNode[id] || 0 }
  }
  return {
    tokens: pick(total.total_tokens),
    input: pick(total.input_tokens),
    output: pick(total.output_tokens),
    cost: priced ? cost : null,
    nodes
  }
}

/** "$0.042", "$1.20" */
export function formatCost(usd) {
  if (!Number.isFinite(usd)) return '—'
  return `$${usd < 0.1 ? usd.toFixed(3) : usd.toFixed(2)}`
}

/** "1m 05s", "42s", "1h 03m" */
export function formatSpan(ms) {
  if (!Number.isFinite(ms) || ms < 0) return '—'
  const total = Math.round(ms / 1000)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h) return `${h}h ${String(m).padStart(2, '0')}m`
  if (m) return `${m}m ${String(s).padStart(2, '0')}s`
  return `${s}s`
}

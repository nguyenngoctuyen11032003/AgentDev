// What happened in the current run, per workflow step: the Kanban board and the
// dashboard both read from here. It is fed by the same WebSocket events that drive the
// chat and the office (node start/end, model and tool calls, handoffs, human input),
// including the replay of a saved session, so reopening a run rebuilds the board.
// A session can hold several turns (a follow-up message runs the team again): `state` is
// always the current turn, and the finished turns before it are kept in `state.turns`, so
// the board and the dashboard can show the whole session. Only a new session resets it.
import { reactive } from 'vue'

const MAX_EVENTS = 300
// Only the latest turns of a long session are kept, so memory stays bounded
const MAX_TURNS = 20
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
    inputs: 0,
    // The lead ended this turn with a plan that waits for your approval: { id, node, summary, plan }
    plan: null,
    turn: 0, // number of the current turn (1-based), 0 before the first task
    turns: [] // earlier turns of this session, oldest first (same fields as above)
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
      turn: state.turn || 1,
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

  // `status`: 'done', or 'cancelled' for a step cut short by Stop (it reported nothing)
  const nodeEnd = (id, output, at, { status = 'done' } = {}) => {
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
    run.status = status
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

  // The server turned an answer down: it does not count (its event goes too)
  // `stillWaiting`: steps that keep waiting for an answer
  const undoInput = (stillWaiting = []) => {
    if (state.inputs > 0) state.inputs -= 1
    for (const id of stillWaiting) if (state.nodes[id]) state.nodes[id].waiting = true
    for (let i = state.events.length - 1; i >= 0; i -= 1) {
      if (state.events[i].kind === 'input') {
        state.events.splice(i, 1)
        break
      }
    }
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

  // `closeOpen`: a turn that never recorded its end (the server went away mid-run) is
  // closed as stopped, so the new request starts its own turn instead of joining it
  const begin = (text, attachments = [], at, { closeOpen = false } = {}) => {
    const time = toMs(at)
    if (closeOpen && state.task && !state.outcome) finish('cancelled', { at: lastEventAt() || undefined })
    // A new task in a finished session is its next turn: the finished one is kept
    if (state.outcome) archiveTurn()
    // Whatever you say next answers the plan (approval or changes): it no longer waits
    state.plan = null
    const previous = state.turns[state.turns.length - 1]
    state.turn = (previous?.number || state.turns.length) + 1
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

  // `settled`: the run already ended elsewhere (a replayed session the server is no longer
  // running, e.g. one cut by a restart): it ends with its last event, never "now"
  const finish = (outcome, { summary = '', error = '', tokenUsage = null, at, settled = false } = {}) => {
    // Completion messages carry no time: while a step is still open it is "now" (live
    // stop); otherwise the run ended with its last event (also right for replays).
    const stillOpen = !settled && Object.values(state.nodes).some((node) => openRun(node))
    const time = at ? toMs(at) : stillOpen ? Date.now() : lastEventAt() || (settled && state.task?.at) || Date.now()
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

  // The lead proposed a plan and waits for your go-ahead
  const proposePlan = ({ id, node = '', summary = '', plan = '' } = {}) => {
    state.plan = { id, node, summary, plan }
  }

  const TURN_FIELDS = ['startedAt', 'endedAt', 'outcome', 'task', 'summary', 'error', 'tokenUsage', 'nodes', 'events', 'inputs', 'plan']
  const archiveTurn = () => {
    const done = { number: state.turn || state.turns.length + 1 }
    for (const key of TURN_FIELDS) done[key] = state[key]
    state.turns.push(done)
    if (state.turns.length > MAX_TURNS) state.turns.splice(0, state.turns.length - MAX_TURNS)
    clearTurn()
  }

  // A new session: every turn goes
  const reset = () => {
    clearTurn()
    state.turn = 0
    state.turns = []
  }

  const clearTurn = () => {
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
    state.plan = null
  }

  return { state, begin, nodeStart, activity, nodeEnd, waitingInput, inputSent, undoInput, assign, handoff, finish, proposePlan, reset }
}

// ---------------------------------------------------------------- derived views

/** Every turn of the session, oldest first; the last one is the current turn (live). */
export function sessionTurns(state) {
  const turns = (state?.turns || []).map((turn, i) => ({ ...turn, number: turn.number || i + 1, current: false }))
  if (state && (state.task || state.startedAt || Object.keys(state.nodes || {}).length)) {
    turns.push({
      number: state.turn || turns.length + 1,
      current: true,
      startedAt: state.startedAt,
      endedAt: state.endedAt,
      outcome: state.outcome,
      task: state.task,
      summary: state.summary,
      error: state.error,
      tokenUsage: state.tokenUsage,
      nodes: state.nodes,
      events: state.events,
      inputs: state.inputs
    })
  }
  return turns
}

/** Working time of one turn (ms): from its task to its end, or to `now` while it runs. */
export function turnSpan(turn, now = Date.now()) {
  return turn?.startedAt ? Math.max(0, (turn.endedAt || now) - turn.startedAt) : 0
}

/**
 * Several turns as one run record (same shape as the tracker state): the runs of a step
 * follow each other across turns (renumbered, each keeps its `turn`), events are joined
 * and token usage is added up; task, outcome and summary are those of the last turn.
 */
export function combineTurns(turns) {
  const list = turns || []
  if (list.length === 1) return { ...list[0], turns: [] }
  const last = list[list.length - 1] || {}
  const nodes = {}
  const events = []
  let inputs = 0
  for (const turn of list) {
    inputs += turn.inputs || 0
    events.push(...(turn.events || []))
    for (const [id, node] of Object.entries(turn.nodes || {})) {
      if (!nodes[id]) nodes[id] = { runs: [], waiting: false, lastAt: null, pendingTask: '' }
      const merged = nodes[id]
      for (const run of node.runs) merged.runs.push({ ...run, turn: run.turn || turn.number, index: merged.runs.length + 1 })
      if (turn === last) merged.waiting = node.waiting
      if (node.lastAt && (!merged.lastAt || node.lastAt > merged.lastAt)) merged.lastAt = node.lastAt
    }
  }
  return {
    startedAt: list.find((turn) => turn.startedAt)?.startedAt || null,
    endedAt: last.endedAt || null,
    outcome: last.outcome || '',
    task: last.task || null,
    summary: last.summary || '',
    error: last.error || '',
    tokenUsage: combineUsage(list.map((turn) => turn.tokenUsage)),
    nodes,
    events,
    inputs,
    number: last.number || 0,
    turns: []
  }
}

// Token reports of several turns added up, in the shape usageTotals reads
function combineUsage(reports) {
  const present = reports.filter(Boolean)
  if (present.length < 2) return present[0] || null
  const total = { total_tokens: 0, input_tokens: 0, output_tokens: 0 }
  const nodeUsages = {}
  const calls = []
  for (const usage of present) {
    const sums = usage?.total_usage || usage?.total || usage?.totals || usage || {}
    for (const key of Object.keys(total)) total[key] += Number.isFinite(sums[key]) ? sums[key] : 0
    if (Array.isArray(usage?.call_history)) calls.push(...usage.call_history)
    for (const [id, item] of Object.entries(usage?.node_usages || {})) {
      const tokens = Number.isFinite(item?.total_tokens) ? item.total_tokens : 0
      nodeUsages[id] = { total_tokens: (nodeUsages[id]?.total_tokens || 0) + tokens }
    }
  }
  return { total_usage: total, call_history: calls, node_usages: nodeUsages }
}

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

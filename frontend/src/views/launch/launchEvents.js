// Pure decisions of the Launch view's event handler (processMessage in LaunchView.vue).
// Each function reads an event (and, where needed, a read-only snapshot of the view's
// state) and says what should happen; the view carries it out. No Vue, no i18n, no I/O,
// so the rules can be unit tested (see launchEvents.test.js).
import { RUN_STATUS, SERVER_STATUS, isRestartInterruption } from '@/components/launch/runStatus.js'

const LIVE_SERVER_STATUSES = ['running', 'waiting_for_input', 'cancelling']

/** Server statuses during which a run is still going (it can be stopped, or waits for you). */
export const isLiveServerStatus = (status) => LIVE_SERVER_STATUSES.includes(status)

/**
 * A replayed `user_message`: its text and attachment names.
 * @returns {{ text: string, names: string[] }}
 */
export const userMessageParts = (data) => ({
  text: data?.text || '',
  names: Array.isArray(data?.attachments) ? data.attachments : []
})

/**
 * The first message of a run is the task, later ones are replies to the agents; a message
 * after a finished run opens the next turn of the session. A reply only answers a question
 * that is pending: a request while nobody waits is a new turn, even when the turn before
 * never recorded its end (e.g. the server restarted).
 * @param {{ task?: unknown, outcome?: unknown, nodes?: Record<string, { waiting?: boolean }> }} trackerState
 * @returns {'reply' | 'new_turn'}
 */
export const userMessageRole = (trackerState) => {
  const awaitingAnswer = Object.values(trackerState?.nodes || {}).some((node) => node.waiting)
  return trackerState?.task && !trackerState?.outcome && awaitingAnswer ? 'reply' : 'new_turn'
}

/**
 * What a `session_resumed` event restores, from its data alone.
 * @param {object} data the event's data (status, error_message, current_node_id, ...)
 * @param {{ hasOpenTurn?: boolean }} [snapshot] hasOpenTurn: the run record has a task without outcome
 */
export const resumedSessionPlan = (data, { hasOpenTurn = false } = {}) => {
  const serverStatus = data?.status
  const isLive = isLiveServerStatus(serverStatus)
  const restarted = isRestartInterruption(data?.error_message)
  // The replay never recorded the end of the last turn, but the server is not running it
  const closeOutcome = !isLive && hasOpenTurn
    ? ({ completed: 'completed', error: 'error' }[serverStatus] || 'cancelled')
    : null
  return {
    // An unknown server status reads as just connected
    status: SERVER_STATUS[serverStatus] || RUN_STATUS.CONNECTED,
    hasLaunched: Boolean(serverStatus) && serverStatus !== 'idle',
    running: isLive,
    stopping: serverStatus === 'cancelling',
    isLive,
    restarted,
    closeOutcome,
    // Nothing runs any more: tool problems of the replay no longer count as being handled
    settleToolIssues: isLive ? null : { recovered: serverStatus === 'completed' },
    // The replay left turns open (the run was cut off): close them at their last activity
    settleOpenTurns: !isLive || restarted,
    markTurnsInterrupted: serverStatus !== 'completed',
    glow: serverStatus === 'waiting_for_input' || serverStatus === 'idle',
    restoreProjects: serverStatus === 'idle',
    restoreComposerAttachments: serverStatus === 'waiting_for_input',
    downloadable: ['completed', 'error', 'cancelled'].includes(serverStatus),
    activeNode: isLive && data?.current_node_id ? data.current_node_id : null,
    notice: restarted ? 'interrupted' : (serverStatus === 'running' || serverStatus === 'waiting_for_input') ? 'reconnected' : null
  }
}

/**
 * A `human_input_required` event: the text to show and whether it only repeats the agent's
 * last reply (a human step usually gets that reply as its input).
 * @param {Array<object>} messages the chat rows
 * @param {object} data the event's data (task_description, input)
 * @param {(text: unknown) => unknown} localizeInput localizes the input's section headers
 */
export const humanInputPrompt = (messages, data, localizeInput = (text) => text) => {
  let lastAgentBubble = null
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].type !== 'dialogue') continue
    lastAgentBubble = messages[i].isRight ? null : messages[i].text ? messages[i] : null
    break
  }
  const rawInput = data?.input
  const localizedInput = localizeInput(rawInput)
  const lastText = String(lastAgentBubble?.text || '').trim()
  const repeatsLast = Boolean(lastText) &&
    [rawInput, localizedInput].some((part) => typeof part === 'string' && part.trim() === lastText)
  const fullMessage = [data?.task_description, repeatsLast ? null : localizedInput]
    .filter((part) => part !== null && part !== undefined && String(part).trim())
    .join('\n\n')
  return { lastAgentBubble, repeatsLast, fullMessage }
}

/**
 * What kind of question a `human_input_required` event opens: an approval gate of the workflow
 * (a Human node), and whether the step after it costs money or cannot be undone (`paid: true`).
 * A lead's question is never a paid gate.
 * @param {object} data the event's data (node_type, paid)
 */
export const gateInfo = (data) => {
  const isGate = data?.node_type === 'human'
  return { isGate, paid: isGate && data?.paid === true }
}

/** One file of an `artifact_created` event, with its defaults filled in. */
export const artifactFile = (event, fallbackSender) => {
  const fileName = event?.file_name || 'artifact'
  const mimeType = event?.mime_type || ''
  return {
    nodeId: event?.node_id,
    nodeName: event?.node_id || fallbackSender,
    fileName,
    mimeType,
    attachmentId: event?.attachment_id,
    // A file of a project opened in place: opens on this machine instead of downloading
    openLocal: !!event?.extra?.open_local,
    relativePath: event?.relative_path || fileName,
    isImage: !!mimeType && mimeType.includes('image')
  }
}

/**
 * The warning/notice side of a `log` event (checked before, and independently of, the INFO side).
 * @returns {null | { kind: 'account', event: string, params: object, level: 'warning' | 'error' }
 *   | { kind: 'tool_failure' } | { kind: 'backend', level: 'warning' | 'error' }}
 */
export const logAlert = (msg) => {
  if (msg?.type !== 'log') return null
  const data = msg.data
  const accountEvent = data?.details?.event
  if (accountEvent === 'account_fallback' || accountEvent === 'account_exhausted') {
    const details = data.details
    return {
      kind: 'account',
      event: accountEvent,
      params: { from: details.from || '', to: details.to || '', model: details.model || '' },
      level: accountEvent === 'account_fallback' ? 'warning' : 'error'
    }
  }
  if (data.level === 'WARNING' || data.level === 'ERROR') {
    // A failed tool call is fed back to the agent, which retries on its own
    if (data.event_type === 'TOOL_CALL') return { kind: 'tool_failure' }
    return { kind: 'backend', level: data.level === 'WARNING' ? 'warning' : 'error' }
  }
  return null
}

/**
 * What an INFO `log` line is, in the order the chat checks it.
 * @param {object} data the log's data
 * @param {{ setupLogRe?: RegExp, logEventKeys?: object, turnHasAgentBubble?: () => boolean }} [rules]
 * @returns {'node_start' | 'model_call' | 'tool_call' | 'node_end' | 'handoff' | 'quiet' | 'memory' | 'notice' | 'ignored'}
 */
export const infoLogKind = (data, { setupLogRe = null, logEventKeys = {}, turnHasAgentBubble = () => false } = {}) => {
  const eventType = data?.event_type
  if (eventType === 'NODE_START') return 'node_start'
  if (eventType === 'MODEL_CALL') return 'model_call'
  if (eventType === 'TOOL_CALL') return 'tool_call'
  if (eventType === 'NODE_END') return 'node_end'
  // An edge fired: built only from this structured event ("Edge condition met" lines also
  // come for edges with trigger: false, which hand nothing over)
  if (eventType === 'HANDOFF') return 'handoff'
  if (data.message && data.message.includes('Edge condition met for')) return 'quiet'
  // "Received your input for CTO": your own bubble already says it
  if (eventType === 'HUMAN_INTERACTION') return 'quiet'
  // The turn's bubble already shows the run working and done; the end line stays only for a
  // turn where no agent said anything
  if (eventType === 'WORKFLOW_START' || (eventType === 'WORKFLOW_END' && turnHasAgentBubble())) return 'quiet'
  if (eventType === 'MEMORY_OPERATION' || eventType === 'THINKING_PROCESS') return 'memory'
  // Set-up chatter ("Global memory 'X' built successfully", ...)
  if (!eventType && setupLogRe && setupLogRe.test(data.message || '')) return 'quiet'
  // Only logs the UI knows how to say: a mapped event type or a tagged event
  if (data.message && (logEventKeys[eventType] || data.details?.event)) return 'notice'
  return 'ignored'
}

/** i18n key of a memory / reflection step's label. */
export const memoryStepLabelKey = (eventType, details) => {
  if (eventType === 'THINKING_PROCESS') return 'launch.activity_done.reflect'
  return String(details?.operation_type || '').toUpperCase() === 'RETRIEVE'
    ? 'launch.activity_done.memory_read'
    : 'launch.activity_done.memory_write'
}

/** "Still thinking (N+ min)" comes back every few minutes: one line per agent, kept current. */
export const noticeCoalesceKey = (data) => (data?.details?.event === 'cli_idle' ? `idle:${data?.node_id || ''}` : '')

/**
 * The engine's "Cancellation requested for workflow ..." line: the run is being stopped (pressed
 * here, elsewhere, or replayed on reload, where nothing else says so before the steps end).
 */
export const isCancelRequestLog = (data) =>
  typeof data?.message === 'string' && data.message.startsWith('Cancellation requested')

/**
 * How a NODE_END ends. A member (delegated) cut short by Stop has nothing to hand over;
 * an optional step that failed (continue_on_error) ends with failed: true and is not done.
 * A step that ends with nothing while the run is being stopped was cut short too.
 * @param {object} details the log's details
 * @param {{ delegatedBy?: string, stopping?: boolean }} snapshot stopping: Stop was pressed here,
 *   the engine said cancellation was requested, or the run was already stopped (a late end)
 */
export const nodeEndOutcome = (details = {}, { delegatedBy = '', stopping = false } = {}) => {
  const flagged = details.cancelled === true || details.status === 'cancelled'
  const memberCancelled = Boolean(delegatedBy) && (flagged || stopping)
  const memberReported = Boolean(delegatedBy) && !memberCancelled && details.output_count !== 0
  const leadCutShort = !delegatedBy && (flagged || (stopping && details.output_count === 0))
  const endStatus = memberCancelled || leadCutShort ? 'cancelled' : (details.failed ? 'error' : 'done')
  return { memberCancelled, memberReported, endStatus }
}

/**
 * The two ends of a handoff: from a HANDOFF log line (details {from, to}) or a top-level
 * `handoff` event ({type: 'handoff', data: {from, to, timestamp}}).
 * @returns {{ from: string | undefined, to: string | undefined, timestamp: string | undefined } | null}
 */
export const handoffOf = (msg) => {
  if (msg?.type === 'handoff') {
    const data = msg.data || msg
    return { from: data.from, to: data.to, timestamp: data.timestamp }
  }
  if (msg?.type === 'log' && msg.data?.event_type === 'HANDOFF') {
    const { from, to } = msg.data.details || {}
    return { from, to, timestamp: msg.data.timestamp }
  }
  return null
}

/**
 * `workflow_completed`: the backend summary is technical and the WORKFLOW_END line already
 * said the run is over, so a "completed" line is added only when nothing did. A turn that
 * ended with a plan waiting for approval drops the end line ("finished" would mislead).
 * turnHasAgentBubble is a function, asked only when it matters.
 */
export const completionNotice = ({ lastMessage, endLine, hasPlan, turnHasAgentBubble }) => {
  const isEndLine = lastMessage?.type === 'notification' && lastMessage.message === endLine
  if (hasPlan) return { dropEndLine: isEndLine, addCompleted: false }
  return { dropEndLine: false, addCompleted: !isEndLine && !turnHasAgentBubble() }
}

/**
 * Which kind of `error` event this is.
 * - run_in_progress: a follow-up turned down because a run is still going (a notice)
 * - note_not_running: a note that arrived after the run ended (goes back to the box)
 * - rejected: a request turned down, the run carries on (fatal: false)
 * - fatal: the run failed
 */
export const errorKind = (data) => {
  if (data?.code === 'run_in_progress') return 'run_in_progress'
  if (data?.code === 'not_running' && data?.note_id) return 'note_not_running'
  if (data?.fatal === false) return 'rejected'
  return 'fatal'
}

/**
 * A step that only forwards text (e.g. a passthrough "Chat Reply" end node) repeats the reply the
 * user just read. True when `text` is the same as the latest agent reply of this turn (after the
 * user's last message), so the chat does not show the same answer twice.
 */
export const isEchoOfLastReply = (messages, text, { userSender = '' } = {}) => {
  const wanted = typeof text === 'string' ? text.trim() : ''
  if (!wanted) return false
  for (let i = (messages?.length || 0) - 1; i >= 0; i -= 1) {
    const message = messages[i]
    if (message?.type !== 'dialogue') continue
    if (message.isRight || message.name === userSender) return false
    if (typeof message.text === 'string' && message.text.trim()) return message.text.trim() === wanted
  }
  return false
}

// Server session states in which a stopped run is still winding down
const STOP_PENDING_STATUSES = ['running', 'waiting_for_input', 'cancelling']

/**
 * Stop was pressed but the server never confirmed it: what its status answer means.
 * 'wait' while the run is still winding down there, 'stopped' once it has ended,
 * 'unknown' when the answer has no status (keep asking until the give-up time).
 */
export const stopCheckOutcome = (data) => {
  const status = data?.status
  if (!status) return 'unknown'
  return STOP_PENDING_STATUSES.includes(status) ? 'wait' : 'stopped'
}

/**
 * After the screen gave up waiting for a stop confirmation, the server may still send the
 * end of that run. 'drop' for its activity (no new spinners), 'close' for its final event
 * (the turn is already recorded as stopped, so the status must not flip), 'keep' otherwise.
 */
export const lateStopEvent = (msg) => {
  const type = msg?.type
  if (type === 'workflow_completed' || type === 'workflow_cancelled') return 'close'
  if (type === 'error' && errorKind(msg?.data) === 'fatal') return 'close'
  if (type === 'log' || type === 'human_input_required' || type === 'handoff' || type === 'plan_proposed') return 'drop'
  return 'keep'
}

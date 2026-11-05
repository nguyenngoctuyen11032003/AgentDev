import { describe, it, expect } from 'vitest'
import { RUN_STATUS } from '@/components/launch/runStatus.js'
import { createRunTracker, stepStatus } from '@/utils/runTracker.js'
import {
  isLiveServerStatus,
  userMessageParts,
  userMessageRole,
  resumedSessionPlan,
  humanInputPrompt,
  artifactFile,
  logAlert,
  infoLogKind,
  memoryStepLabelKey,
  noticeCoalesceKey,
  nodeEndOutcome,
  isCancelRequestLog,
  handoffOf,
  completionNotice,
  errorKind
} from './launchEvents.js'

const log = (level, eventType, extra = {}) => ({
  type: 'log',
  data: { level, event_type: eventType, node_id: 'CTO', message: 'line', details: {}, timestamp: '2026-01-01T00:00:00Z', ...extra }
})

describe('log events', () => {
  it('classifies INFO lines by event type, in the chat order', () => {
    const kind = (eventType, extra) => infoLogKind(log('INFO', eventType, extra).data)
    expect(kind('NODE_START')).toBe('node_start')
    expect(kind('MODEL_CALL')).toBe('model_call')
    expect(kind('TOOL_CALL')).toBe('tool_call')
    expect(kind('NODE_END')).toBe('node_end')
    expect(kind('HANDOFF')).toBe('handoff')
    expect(kind('HUMAN_INTERACTION')).toBe('quiet')
    expect(kind('WORKFLOW_START')).toBe('quiet')
    expect(kind('MEMORY_OPERATION')).toBe('memory')
    expect(kind('THINKING_PROCESS')).toBe('memory')
  })

  it('keeps "Edge condition met" lines out of the chat (only HANDOFF hands over)', () => {
    expect(infoLogKind({ event_type: 'EDGE_EVALUATION', message: 'Edge condition met for A -> B' })).toBe('quiet')
  })

  it('shows the run end line only when no agent spoke in the turn', () => {
    const data = { event_type: 'WORKFLOW_END', message: 'Workflow finished' }
    const logEventKeys = { WORKFLOW_END: 'launch.log_events.workflow_end' }
    expect(infoLogKind(data, { logEventKeys, turnHasAgentBubble: () => true })).toBe('quiet')
    expect(infoLogKind(data, { logEventKeys, turnHasAgentBubble: () => false })).toBe('notice')
  })

  it('asks turnHasAgentBubble only for WORKFLOW_END', () => {
    let asked = 0
    infoLogKind({ event_type: 'NODE_START' }, { turnHasAgentBubble: () => { asked += 1; return true } })
    expect(asked).toBe(0)
  })

  it('drops set-up chatter and unmapped engine bookkeeping, keeps tagged events', () => {
    const setupLogRe = /^(Global memory '.*' built successfully|Memory manager built for node )/
    expect(infoLogKind({ message: "Global memory 'x' built successfully" }, { setupLogRe })).toBe('quiet')
    expect(infoLogKind({ message: 'Executing node X with edge dynamic config' }, { setupLogRe })).toBe('ignored')
    expect(infoLogKind({ message: 'Still thinking', details: { event: 'cli_idle' } }, { setupLogRe })).toBe('notice')
    expect(infoLogKind({ event_type: 'NODE_SKIPPED', message: 'skipped' }, { logEventKeys: { NODE_SKIPPED: 'k' } })).toBe('notice')
    expect(infoLogKind({ event_type: 'NODE_SKIPPED', message: '' }, { logEventKeys: { NODE_SKIPPED: 'k' } })).toBe('ignored')
  })

  it('coalesces "still thinking" lines per agent', () => {
    expect(noticeCoalesceKey({ node_id: 'CTO', details: { event: 'cli_idle' } })).toBe('idle:CTO')
    expect(noticeCoalesceKey({ details: { event: 'cli_idle' } })).toBe('idle:')
    expect(noticeCoalesceKey({ node_id: 'CTO', details: {} })).toBe('')
  })

  it('labels memory and reflection steps', () => {
    expect(memoryStepLabelKey('THINKING_PROCESS', {})).toBe('launch.activity_done.reflect')
    expect(memoryStepLabelKey('MEMORY_OPERATION', { operation_type: 'retrieve' })).toBe('launch.activity_done.memory_read')
    expect(memoryStepLabelKey('MEMORY_OPERATION', { operation_type: 'UPDATE' })).toBe('launch.activity_done.memory_write')
    expect(memoryStepLabelKey('MEMORY_OPERATION', undefined)).toBe('launch.activity_done.memory_write')
  })
})

describe('log alerts (warnings, errors, accounts)', () => {
  it('reports an account switch or an exhausted account', () => {
    const fallback = log('WARNING', null, { details: { event: 'account_fallback', from: 'a', to: 'b', model: 'm' } })
    expect(logAlert(fallback)).toEqual({ kind: 'account', event: 'account_fallback', params: { from: 'a', to: 'b', model: 'm' }, level: 'warning' })
    const exhausted = log('INFO', null, { details: { event: 'account_exhausted' } })
    expect(logAlert(exhausted)).toEqual({ kind: 'account', event: 'account_exhausted', params: { from: '', to: '', model: '' }, level: 'error' })
  })

  it('groups failed tool calls apart from other warnings and errors', () => {
    expect(logAlert(log('WARNING', 'TOOL_CALL'))).toEqual({ kind: 'tool_failure' })
    expect(logAlert(log('ERROR', 'TOOL_CALL'))).toEqual({ kind: 'tool_failure' })
    expect(logAlert(log('WARNING', null))).toEqual({ kind: 'backend', level: 'warning' })
    expect(logAlert(log('ERROR', 'NODE_END'))).toEqual({ kind: 'backend', level: 'error' })
  })

  it('has nothing to say for INFO lines and other events', () => {
    expect(logAlert(log('INFO', 'NODE_START'))).toBeNull()
    expect(logAlert({ type: 'workflow_completed', data: {} })).toBeNull()
  })
})

describe('handoff', () => {
  it('reads the structured HANDOFF log line', () => {
    const msg = log('INFO', 'HANDOFF', { details: { from: 'CTO', to: 'QA' }, timestamp: 't1' })
    expect(handoffOf(msg)).toEqual({ from: 'CTO', to: 'QA', timestamp: 't1' })
  })

  it('reads a top-level handoff event, with or without a data envelope', () => {
    expect(handoffOf({ type: 'handoff', data: { from: 'A', to: 'B', timestamp: 't' } })).toEqual({ from: 'A', to: 'B', timestamp: 't' })
    expect(handoffOf({ type: 'handoff', from: 'A', to: 'B' })).toEqual({ from: 'A', to: 'B', timestamp: undefined })
  })

  it('ignores other lines', () => {
    expect(handoffOf(log('INFO', 'NODE_START'))).toBeNull()
    expect(handoffOf({ type: 'log', data: { event_type: 'HANDOFF' } })).toEqual({ from: undefined, to: undefined, timestamp: undefined })
  })
})

describe('node end', () => {
  it('a lead ends done, or error when an optional step failed', () => {
    expect(nodeEndOutcome({ output: 'x' })).toEqual({ memberCancelled: false, memberReported: false, endStatus: 'done' })
    expect(nodeEndOutcome({ failed: true })).toMatchObject({ endStatus: 'error' })
  })

  it('a member reports to its lead unless it had no output', () => {
    expect(nodeEndOutcome({ output_count: 2 }, { delegatedBy: 'CTO' })).toEqual({ memberCancelled: false, memberReported: true, endStatus: 'done' })
    expect(nodeEndOutcome({ output_count: 0 }, { delegatedBy: 'CTO' })).toMatchObject({ memberReported: false })
  })

  it('a member cut short by Stop is cancelled and reports nothing', () => {
    expect(nodeEndOutcome({}, { delegatedBy: 'CTO', stopping: true })).toEqual({ memberCancelled: true, memberReported: false, endStatus: 'cancelled' })
    expect(nodeEndOutcome({ status: 'cancelled' }, { delegatedBy: 'CTO' })).toMatchObject({ endStatus: 'cancelled' })
    expect(nodeEndOutcome({ cancelled: true }, { delegatedBy: 'CTO' })).toMatchObject({ endStatus: 'cancelled' })
    // Stop does not cancel a lead's own end
    expect(nodeEndOutcome({}, { stopping: true })).toMatchObject({ memberCancelled: false, endStatus: 'done' })
  })
})

describe('human input', () => {
  const agent = (text) => ({ type: 'dialogue', isRight: false, text })
  const user = (text) => ({ type: 'dialogue', isRight: true, text })
  const note = { type: 'notification', message: 'n' }

  it('shows the task and the input', () => {
    const prompt = humanInputPrompt([agent('Earlier')], { task_description: 'Approve?', input: 'Plan' })
    expect(prompt).toMatchObject({ repeatsLast: false, fullMessage: 'Approve?\n\nPlan' })
    expect(prompt.lastAgentBubble.text).toBe('Earlier')
  })

  it('does not repeat the agent reply that is already the last bubble', () => {
    const prompt = humanInputPrompt([agent('The plan'), note], { input: '  The plan  ' })
    expect(prompt).toMatchObject({ repeatsLast: true, fullMessage: '' })
  })

  it('compares with the localized input too', () => {
    const prompt = humanInputPrompt([agent('Kế hoạch')], { task_description: 'Duyệt?', input: 'Plan' }, () => 'Kế hoạch')
    expect(prompt).toMatchObject({ repeatsLast: true, fullMessage: 'Duyệt?' })
  })

  it('has no agent bubble when the user spoke last', () => {
    const prompt = humanInputPrompt([agent('A'), user('B')], { input: 'A' })
    expect(prompt).toMatchObject({ lastAgentBubble: null, repeatsLast: false, fullMessage: 'A' })
  })
})

describe('session replay (user_message, session_resumed)', () => {
  it('reads a replayed user message', () => {
    expect(userMessageParts({ text: 'Hi', attachments: ['a.md'] })).toEqual({ text: 'Hi', names: ['a.md'] })
    expect(userMessageParts(undefined)).toEqual({ text: '', names: [] })
    expect(userMessageParts({ text: 'Hi', attachments: 'a.md' })).toEqual({ text: 'Hi', names: [] })
  })

  it('a message answers only a pending question of an open turn', () => {
    expect(userMessageRole({ task: { text: 't' }, outcome: null, nodes: { CTO: { waiting: true } } })).toBe('reply')
    expect(userMessageRole({ task: { text: 't' }, outcome: null, nodes: { CTO: { waiting: false } } })).toBe('new_turn')
    expect(userMessageRole({ task: { text: 't' }, outcome: 'completed', nodes: { CTO: { waiting: true } } })).toBe('new_turn')
    expect(userMessageRole({ task: null, nodes: {} })).toBe('new_turn')
  })

  it('a live session keeps running and says it reconnected', () => {
    const plan = resumedSessionPlan({ status: 'running', current_node_id: 'QA' }, { hasOpenTurn: true })
    expect(plan).toMatchObject({
      status: RUN_STATUS.RUNNING, running: true, stopping: false, isLive: true, closeOutcome: null,
      settleToolIssues: null, settleOpenTurns: false, activeNode: 'QA', notice: 'reconnected', hasLaunched: true
    })
  })

  it('a waiting session glows and gives back the composer attachments', () => {
    expect(resumedSessionPlan({ status: 'waiting_for_input' })).toMatchObject({
      status: RUN_STATUS.WAITING_INPUT, running: true, glow: true, restoreComposerAttachments: true, notice: 'reconnected'
    })
  })

  it('a cancelling session is stopping', () => {
    expect(resumedSessionPlan({ status: 'cancelling' })).toMatchObject({ running: true, stopping: true, notice: null })
  })

  it('a finished session closes the open turn with its outcome and settles everything', () => {
    expect(resumedSessionPlan({ status: 'completed' }, { hasOpenTurn: true })).toMatchObject({
      status: RUN_STATUS.COMPLETED, running: false, closeOutcome: 'completed', settleToolIssues: { recovered: true },
      settleOpenTurns: true, markTurnsInterrupted: false, downloadable: true, activeNode: null
    })
    expect(resumedSessionPlan({ status: 'error' }, { hasOpenTurn: true })).toMatchObject({ closeOutcome: 'error', settleToolIssues: { recovered: false }, markTurnsInterrupted: true })
    expect(resumedSessionPlan({ status: 'cancelled' }, { hasOpenTurn: true })).toMatchObject({ closeOutcome: 'cancelled', downloadable: true })
    expect(resumedSessionPlan({ status: 'completed' }, { hasOpenTurn: false })).toMatchObject({ closeOutcome: null })
  })

  it('a session cut by a server restart is closed and says so', () => {
    const plan = resumedSessionPlan({ status: 'error', error_message: 'Interrupted by a server restart' }, { hasOpenTurn: true })
    expect(plan).toMatchObject({ restarted: true, closeOutcome: 'error', notice: 'interrupted', settleOpenTurns: true })
  })

  it('a reopened draft restores its projects; an unknown status reads as connected', () => {
    expect(resumedSessionPlan({ status: 'idle' })).toMatchObject({ status: RUN_STATUS.READY, hasLaunched: false, restoreProjects: true, glow: true, notice: null })
    expect(resumedSessionPlan({ status: 'weird' })).toMatchObject({ status: RUN_STATUS.CONNECTED, hasLaunched: true })
    expect(resumedSessionPlan({})).toMatchObject({ status: RUN_STATUS.CONNECTED, hasLaunched: false })
  })

  it('knows the live server statuses', () => {
    expect(['running', 'waiting_for_input', 'cancelling'].every(isLiveServerStatus)).toBe(true)
    expect(isLiveServerStatus('completed')).toBe(false)
  })
})

describe('workflow completed / cancelled', () => {
  const endLine = 'Run finished'
  it('adds "completed" only when nothing said the run is over', () => {
    expect(completionNotice({ lastMessage: null, endLine, hasPlan: false, turnHasAgentBubble: () => false })).toEqual({ dropEndLine: false, addCompleted: true })
    expect(completionNotice({ lastMessage: { type: 'notification', message: endLine }, endLine, hasPlan: false, turnHasAgentBubble: () => false })).toEqual({ dropEndLine: false, addCompleted: false })
    expect(completionNotice({ lastMessage: null, endLine, hasPlan: false, turnHasAgentBubble: () => true })).toEqual({ dropEndLine: false, addCompleted: false })
  })

  it('a turn ending with a plan drops the end line instead', () => {
    expect(completionNotice({ lastMessage: { type: 'notification', message: endLine }, endLine, hasPlan: true, turnHasAgentBubble: () => false })).toEqual({ dropEndLine: true, addCompleted: false })
    expect(completionNotice({ lastMessage: { type: 'dialogue' }, endLine, hasPlan: true, turnHasAgentBubble: () => false })).toEqual({ dropEndLine: false, addCompleted: false })
  })
})

describe('errors', () => {
  it('tells notices and turned-down requests from fatal errors', () => {
    expect(errorKind({ code: 'run_in_progress' })).toBe('run_in_progress')
    expect(errorKind({ code: 'not_running', note_id: 'n1' })).toBe('note_not_running')
    expect(errorKind({ code: 'not_running' })).toBe('fatal')
    expect(errorKind({ code: 'empty_message', fatal: false })).toBe('rejected')
    expect(errorKind({ message: 'boom' })).toBe('fatal')
    expect(errorKind(undefined)).toBe('fatal')
  })
})

describe('artifacts', () => {
  it('fills in defaults and flags images', () => {
    expect(artifactFile({ node_id: 'CTO', file_name: 'a.png', mime_type: 'image/png', attachment_id: 'x', relative_path: 'out/a.png', extra: { open_local: 1 } }, 'Agent')).toEqual({
      nodeId: 'CTO', nodeName: 'CTO', fileName: 'a.png', mimeType: 'image/png', attachmentId: 'x', openLocal: true, relativePath: 'out/a.png', isImage: true
    })
    expect(artifactFile({}, 'Agent')).toEqual({
      nodeId: undefined, nodeName: 'Agent', fileName: 'artifact', mimeType: '', attachmentId: undefined, openLocal: false, relativePath: 'artifact', isImage: false
    })
  })
})

describe('stop while members work in parallel', () => {
  it('recognises the engine cancel line', () => {
    expect(isCancelRequestLog({ message: 'Cancellation requested for workflow session_1' })).toBe(true)
    expect(isCancelRequestLog({ message: 'Executing node X' })).toBe(false)
    expect(isCancelRequestLog(null)).toBe(false)
  })

  it('members still running when the stop lands end stopped, not done, with or without output', () => {
    for (const details of [{ output_count: 0 }, { output_count: 1, output: 'partial' }, {}]) {
      expect(nodeEndOutcome(details, { delegatedBy: 'Lead', stopping: true })).toEqual({
        memberCancelled: true, memberReported: false, endStatus: 'cancelled'
      })
    }
  })

  it('a lead cut short with nothing to say ends stopped; one that answered stays done', () => {
    expect(nodeEndOutcome({ output_count: 0 }, { stopping: true }).endStatus).toBe('cancelled')
    expect(nodeEndOutcome({ output_count: 1, output: 'x' }, { stopping: true }).endStatus).toBe('done')
    expect(nodeEndOutcome({ output_count: 0 }).endStatus).toBe('done')
  })

  it('replayed: member ends after workflow_cancelled keep "cancelled" on the tracker', () => {
    const tracker = createRunTracker()
    tracker.begin('build it', [], '2026-01-01T00:00:00Z')
    tracker.nodeStart('Lead', '2026-01-01T00:00:01Z')
    tracker.nodeStart('Dev', '2026-01-01T00:00:02Z', { delegatedBy: 'Lead' })
    tracker.nodeStart('QA', '2026-01-01T00:00:02Z', { delegatedBy: 'Lead' })
    // Dev ends while the stop is in flight (the cancel line came first)
    const stopping = true
    tracker.nodeEnd('Dev', '', '2026-01-01T00:00:05Z', { status: nodeEndOutcome({ output_count: 0, delegated_by: 'Lead' }, { delegatedBy: 'Lead', stopping }).endStatus })
    // workflow_cancelled closes the rest
    tracker.finish('cancelled', { at: '2026-01-01T00:00:06Z' })
    // QA's end arrives late: it must not open a new "done" run
    tracker.nodeEnd('QA', 'late', '2026-01-01T00:00:07Z', { status: 'done' })
    expect(stepStatus(tracker.state.nodes.Dev)).toBe('cancelled')
    expect(stepStatus(tracker.state.nodes.QA)).toBe('cancelled')
    expect(tracker.state.nodes.QA.runs).toHaveLength(1)
    expect(stepStatus(tracker.state.nodes.Lead)).toBe('cancelled')
  })
})

import { describe, it, expect } from 'vitest'
import { stopCheckOutcome, lateStopEvent } from '@/views/launch/launchEvents.js'

describe('stopCheckOutcome', () => {
  it('waits while the server is still winding the run down', () => {
    for (const status of ['running', 'waiting_for_input', 'cancelling']) {
      expect(stopCheckOutcome({ status })).toBe('wait')
    }
  })
  it('reports stopped once the server run has ended', () => {
    for (const status of ['cancelled', 'completed', 'error', 'idle']) {
      expect(stopCheckOutcome({ status })).toBe('stopped')
    }
  })
  it('is unknown without a status (session not found, old server)', () => {
    expect(stopCheckOutcome({ message: 'Session not found' })).toBe('unknown')
    expect(stopCheckOutcome(null)).toBe('unknown')
  })
})

describe('lateStopEvent', () => {
  it('drops the activity of a run the screen already marked stopped', () => {
    expect(lateStopEvent({ type: 'log', data: { level: 'INFO' } })).toBe('drop')
    expect(lateStopEvent({ type: 'human_input_required' })).toBe('drop')
  })
  it('closes on the run end, so the status does not flip to completed', () => {
    expect(lateStopEvent({ type: 'workflow_completed' })).toBe('close')
    expect(lateStopEvent({ type: 'workflow_cancelled' })).toBe('close')
    expect(lateStopEvent({ type: 'error', data: { message: 'boom' } })).toBe('close')
  })
  it('keeps everything else (a turned-down request, a new turn, the session list)', () => {
    expect(lateStopEvent({ type: 'error', data: { fatal: false } })).toBe('keep')
    expect(lateStopEvent({ type: 'workflow_started' })).toBe('keep')
    expect(lateStopEvent({ type: 'connection' })).toBe('keep')
  })
})

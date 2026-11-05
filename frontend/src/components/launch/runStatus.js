// Status of the chat "Chạy" screen. Code compares against these constants, never against
// literals: a typo in a hand-written 'Waiting for input...' silently broke a check before.
// The values are the internal tokens the screen already passes to its views (Office,
// Dashboard, Kanban); what the user reads always comes from i18n (STATUS_LABEL_KEYS).
export const RUN_STATUS = Object.freeze({
  NO_WORKFLOW: 'Waiting for workflow selection...',
  NO_FILE: 'Waiting for file selection...',
  CONNECTING: 'Connecting...',
  CONNECTED: 'Connected',
  CONNECTION_ERROR: 'Connection error',
  DISCONNECTED: 'Disconnected',
  READY: 'Waiting for launch...',
  LAUNCHING: 'Launching...',
  RUNNING: 'Running...',
  WAITING_INPUT: 'Waiting for input...',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  FAILED: 'Failed',
  ERROR: 'Error'
})

// Per-step state added on top of the tracker's own ('todo' | 'working' | 'waiting' | 'done' | 'error' | 'cancelled')
export const STEP_STATUS = Object.freeze({ SKIPPED: 'skipped' })

// The server's English reason when a restart cut a run off. Compare through isRestartInterruption;
// the UI shows launch.sessions.interrupted_restart / interrupted_notice instead of this text.
export const SERVER_RESTART_REASON = 'Interrupted by a server restart'
export const isRestartInterruption = (message) => /server restart/i.test(String(message || ''))

// The run phase a status belongs to: idle | running | waiting_input | completed | cancelled | error
export const runPhase = (status) => {
  switch (status) {
    case RUN_STATUS.LAUNCHING:
    case RUN_STATUS.RUNNING:
      return 'running'
    case RUN_STATUS.WAITING_INPUT:
      return 'waiting_input'
    case RUN_STATUS.COMPLETED:
      return 'completed'
    case RUN_STATUS.CANCELLED:
      return 'cancelled'
    case RUN_STATUS.FAILED:
    case RUN_STATUS.ERROR:
      return 'error'
    default:
      return 'idle'
  }
}

// A run is going on (working, or paused on a question to the user)
export const isLiveStatus = (status) => status === RUN_STATUS.RUNNING || status === RUN_STATUS.WAITING_INPUT

// The run ended (finished, stopped or failed): the next message starts a follow-up turn
export const isFinishedStatus = (status) => ['completed', 'cancelled', 'error'].includes(runPhase(status))

// Server session status (session_resumed) -> screen status
export const SERVER_STATUS = Object.freeze({
  idle: RUN_STATUS.READY,
  running: RUN_STATUS.RUNNING,
  waiting_for_input: RUN_STATUS.WAITING_INPUT,
  completed: RUN_STATUS.COMPLETED,
  error: RUN_STATUS.ERROR,
  cancelled: RUN_STATUS.CANCELLED,
  // Stop was pressed and the run is winding down: locked until workflow_cancelled
  cancelling: RUN_STATUS.RUNNING
})

// Status -> i18n key of its label (older aliases kept for saved/legacy values)
export const STATUS_LABEL_KEYS = Object.freeze({
  [RUN_STATUS.NO_WORKFLOW]: 'launch.status_waiting_workflow',
  [RUN_STATUS.NO_FILE]: 'launch.status_waiting_file',
  'Pending workflow selection': 'launch.status_waiting_workflow',
  'Pending file selection': 'launch.status_waiting_file',
  [RUN_STATUS.CONNECTING]: 'launch.status_connecting',
  [RUN_STATUS.CONNECTED]: 'launch.status_connected',
  [RUN_STATUS.CONNECTION_ERROR]: 'launch.status_connection_error',
  [RUN_STATUS.DISCONNECTED]: 'launch.status_disconnected',
  [RUN_STATUS.READY]: 'launch.status_waiting_launch',
  'Pending launch': 'launch.status_waiting_launch',
  [RUN_STATUS.LAUNCHING]: 'launch.status_launching',
  [RUN_STATUS.RUNNING]: 'launch.status_running',
  'In Progress': 'launch.status_running',
  [RUN_STATUS.WAITING_INPUT]: 'launch.status_waiting_input',
  [RUN_STATUS.COMPLETED]: 'launch.status_completed',
  [RUN_STATUS.CANCELLED]: 'launch.status_cancelled',
  [RUN_STATUS.FAILED]: 'launch.status_failed',
  [RUN_STATUS.ERROR]: 'launch.status_error'
})

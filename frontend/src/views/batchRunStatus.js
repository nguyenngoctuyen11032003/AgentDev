import { localizeBackendError } from '@/utils/errorTranslate.js'

// Status of the Batch Run screen. Code compares against these constants, never against literals;
// what the user reads always comes from i18n (batchStatusLabelKey).
export const BATCH_STATUS = Object.freeze({
  IDLE: 'idle',
  PENDING_WORKFLOW: 'pending_workflow',
  PENDING_FILE: 'pending_file',
  CONNECTING: 'connecting',
  PENDING_LAUNCH: 'pending_launch',
  LAUNCHING: 'launching',
  IN_PROGRESS: 'in_progress',
  COMPLETED: 'completed',
  CANCELLED: 'cancelled',
  FAILED: 'failed',
  ERROR: 'error',
  DISCONNECTED: 'disconnected',
  CONNECTION_ERROR: 'connection_error'
})

const LABEL_KEYS = Object.freeze({
  [BATCH_STATUS.IDLE]: 'batch_run.status_idle',
  [BATCH_STATUS.PENDING_WORKFLOW]: 'batch_run.status_waiting_workflow',
  [BATCH_STATUS.PENDING_FILE]: 'batch_run.status_waiting_file',
  [BATCH_STATUS.CONNECTING]: 'launch.status_connecting',
  [BATCH_STATUS.PENDING_LAUNCH]: 'launch.status_waiting_launch',
  [BATCH_STATUS.LAUNCHING]: 'launch.status_launching',
  [BATCH_STATUS.IN_PROGRESS]: 'batch_run.status_in_progress',
  [BATCH_STATUS.COMPLETED]: 'batch_run.status_completed',
  [BATCH_STATUS.CANCELLED]: 'batch_run.status_cancelled',
  [BATCH_STATUS.FAILED]: 'launch.status_failed',
  [BATCH_STATUS.ERROR]: 'launch.status_error',
  [BATCH_STATUS.DISCONNECTED]: 'launch.status_disconnected',
  [BATCH_STATUS.CONNECTION_ERROR]: 'launch.status_connection_error'
})

// i18n key of a status; an unknown value falls back to the idle label, never the raw text.
export const batchStatusLabelKey = (status) => LABEL_KEYS[status] || LABEL_KEYS[BATCH_STATUS.IDLE]

export const isBatchFinished = (status) =>
  status === BATCH_STATUS.COMPLETED || status === BATCH_STATUS.CANCELLED

// Detail to show after a localized summary. A thrown exception's own message is a technical
// string (never shown); a backend result's `detail` goes through the shared error translator.
export const batchErrorDetail = (result) => {
  if (!result || result instanceof Error) return ''
  const raw = result.detail
  if (raw === undefined || raw === null || raw === '') return ''
  let text
  if (typeof raw === 'string') text = raw
  else if (Array.isArray(raw)) {
    text = raw.map((item) => (typeof item === 'string' ? item : (item?.msg || item?.message || ''))).filter(Boolean).join('; ')
  } else text = raw.message || raw.msg || ''
  return text ? (localizeBackendError(text) || text) : ''
}

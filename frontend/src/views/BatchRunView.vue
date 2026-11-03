<template>
  <div class="launch-view">
    <div class="launch-bg"></div>
    <div class="header">
      <h1>{{ $t('batch_run.title') }}</h1>
      <button
        type="button"
        class="btn ghost icon-only settings-button"
        :aria-label="$t('batch_run.batch_settings')"
        :title="$t('batch_run.batch_settings')"
        @click="showBatchSettingsModal()"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="3"></circle>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
        </svg>
      </button>
    </div>
    <div class="content">
      <!-- Left panel -->
      <div class="left-panel">
        <!-- Log area -->
        <div v-show="viewMode === 'terminal'" class="log-box">
          <div class="log-toolbar">
            <button type="button" class="btn ghost sm log-tool" :disabled="logMessages.length === 0" @click="copyLogs">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"></rect><path d="M5 15V6a2 2 0 0 1 2-2h9"></path></svg>
              {{ $t('batch_run.copy_logs') }}
            </button>
            <button type="button" class="btn ghost sm log-tool" :disabled="logMessages.length === 0" @click="clearLogs">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"></path></svg>
              {{ $t('batch_run.clear_logs') }}
            </button>
          </div>
          <div class="log-messages" ref="logMessagesRef" role="log" :aria-label="$t('batch_run.terminal')">
            <div v-for="logMessage in logMessages" :key="logMessage.id" class="log-message">
              <span :class="`log-timestamp log-timestamp-${logMessage.type}`">{{ logMessage.timestamp }}</span>
              <span :class="`log-text log-text-${logMessage.type}`">{{ logMessage.message }}</span>
            </div>
            <div v-if="logMessages.length === 0" class="log-placeholder">
              {{ $t('batch_run.logs_placeholder') }}
            </div>
          </div>
        </div>

        <!-- Dashboard area -->
        <div v-if="viewMode === 'dashboard'" class="dashboard-box">
          <div class="dashboard-content">
            <!-- Progress is the hero -->
            <div class="progress-section">
              <div class="progress-head">
                <span id="batch-progress-label" class="progress-label">{{ $t('batch_run.overall_progress') }}</span>
                <span class="progress-detail">{{ progressDetail }}</span>
              </div>
              <div class="progress-row">
                <div
                  class="progress-bar"
                  role="progressbar"
                  aria-labelledby="batch-progress-label"
                  aria-valuemin="0"
                  aria-valuemax="100"
                  :aria-valuenow="progressPercentage"
                  :aria-valuetext="progressDetail ? `${progressPercentage}% (${progressDetail})` : `${progressPercentage}%`"
                >
                  <div
                    class="progress-fill"
                    :class="{ processing: status === 'In Progress', 'is-done': status === 'Batch completed', 'is-cancelled': status === 'Batch cancelled' }"
                    :style="{ width: progressPercentage + '%' }"
                  ></div>
                </div>
                <div class="progress-text">{{ progressPercentage }}%</div>
              </div>
            </div>

            <!-- Metrics Grid -->
            <div class="metrics-grid">
              <div class="metric-card">
                <div class="metric-title">{{ $t('batch_run.rows_completed') }}</div>
                <div class="metric-value">{{ completedRows }}</div>
              </div>
              <div class="metric-card">
                <div class="metric-title">{{ $t('batch_run.total_time') }}</div>
                <!-- Text is written by the timer loop directly (no per-tick re-render of the view) -->
                <div ref="totalTimeEl" class="metric-value metric-timer"></div>
              </div>
              <div class="metric-card">
                <div class="metric-title">{{ $t('batch_run.success_rate') }}</div>
                <div class="metric-value">{{ successRate }}</div>
              </div>
              <div class="metric-card" :class="{ 'status-active': status === 'In Progress' }">
                <div class="metric-title">{{ $t('batch_run.current_status') }}</div>
                <div class="metric-value metric-status">{{ computedStatus }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right panel -->
      <div class="right-panel">
        <div class="control-section">
          <label class="section-label" for="batch-workflow-input">{{ $t('batch_run.workflow_selection') }}</label>
          <div class="select-wrapper custom-file-selector" ref="fileSelectorWrapperRef">
            <input
              id="batch-workflow-input"
              ref="fileSelectorInputRef"
              v-model="fileSearchQuery"
              type="text"
              class="input file-selector-input"
              role="combobox"
              aria-autocomplete="list"
              aria-haspopup="listbox"
              aria-controls="batch-workflow-listbox"
              :aria-expanded="isFileDropdownOpen ? 'true' : 'false'"
              :aria-activedescendant="activeOptionId"
              autocomplete="off"
              spellcheck="false"
              :placeholder="loading ? $t('batch_run.loading') : $t('batch_run.select_yaml')"
              :disabled="loading || isWorkflowRunning"
              @focus="handleFileInputFocus"
              @input="handleFileInputChange"
              @keydown="handleFileInputKeydown"
              @blur="handleFileInputBlur"
            />
            <svg class="select-arrow" :class="{ open: isFileDropdownOpen }" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"></path></svg>
            <Transition name="file-dropdown">
              <ul
                v-if="isFileDropdownOpen"
                id="batch-workflow-listbox"
                class="file-dropdown"
                role="listbox"
                :aria-label="$t('batch_run.workflow_selection')"
              >
                <li
                  v-for="(workflow, index) in filteredWorkflowFiles"
                  :id="`batch-workflow-option-${index}`"
                  :key="workflow.name"
                  class="file-option"
                  :class="{ active: index === activeOptionIndex, selected: workflow.name === selectedYamlFile }"
                  role="option"
                  :aria-selected="workflow.name === selectedYamlFile ? 'true' : 'false'"
                  @mousedown.prevent="selectWorkflow(workflow.name)"
                  @mousemove="activeOptionIndex = index"
                >
                  <span class="file-name">{{ workflow.name }}</span>
                  <span v-if="workflow.description" class="file-desc">
                    {{ localizedWorkflowDescription(workflow.name, workflow.description) }}
                  </span>
                </li>
                <li v-if="!filteredWorkflowFiles.length" class="file-empty" role="presentation">
                  {{ $t('batch_run.no_results') }}
                </li>
              </ul>
            </Transition>
          </div>

          <span id="batch-input-file-label" class="section-label">{{ $t('batch_run.input_file_selection') }}</span>
          <div class="input-file-section">
            <div class="file-upload-wrapper">
              <input
                ref="inputFileInputRef"
                type="file"
                accept=".xlsx,.csv"
                class="hidden-file-input"
                tabindex="-1"
                aria-hidden="true"
                @change="onInputFileSelected"
              />
              <button
                type="button"
                class="file-upload-button"
                :class="{ 'has-file': selectedInputFile }"
                aria-labelledby="batch-input-file-label"
                aria-describedby="batch-input-file-hint"
                :disabled="loading || isWorkflowRunning"
                @click="handleInputFileButtonClick"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M5 20h14"></path></svg>
                <span class="file-upload-text">{{ selectedInputFile ? selectedInputFile.name : $t('batch_run.select_input_file') }}</span>
              </button>
              <button
                v-if="selectedInputFile"
                type="button"
                class="btn secondary icon-only remove-file-button"
                :aria-label="$t('batch_run.remove_input_file')"
                :title="$t('batch_run.remove_input_file')"
                :disabled="loading || isWorkflowRunning"
                @click="removeInputFile"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"></path></svg>
              </button>
            </div>
            <p id="batch-input-file-hint" class="field-hint">{{ $t('batch_run.input_file_hint') }}</p>
          </div>

          <div class="input-manual">
            <button type="button" class="manual-title" aria-haspopup="dialog" @click="showColumnGuideModal = true">
              {{ $t('batch_run.input_file_format') }}
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="info-icon" aria-hidden="true">
                <circle cx="12" cy="12" r="10"></circle>
                <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
                <path d="M12 17h.01"></path>
              </svg>
            </button>
          </div>

          <span id="batch-view-label" class="section-label">{{ $t('batch_run.view') }}</span>
          <div class="view-toggle" role="group" aria-labelledby="batch-view-label">
            <button
              type="button"
              class="toggle-button"
              :class="{ active: viewMode === 'dashboard' }"
              :aria-pressed="viewMode === 'dashboard' ? 'true' : 'false'"
              @click="switchToDashboard"
            >
              {{ $t('batch_run.dashboard') }}
            </button>
            <button
              type="button"
              class="toggle-button"
              :class="{ active: viewMode === 'terminal' }"
              :aria-pressed="viewMode === 'terminal' ? 'true' : 'false'"
              @click="viewMode = 'terminal'"
            >
              {{ $t('batch_run.terminal') }}
            </button>
          </div>

          <!-- Button area -->
          <div class="button-section">
            <button
              type="button"
              class="btn primary launch-button"
              :class="{ glow: shouldGlow, 'is-sending': isSending }"
              :aria-busy="isSending ? 'true' : 'false'"
              :aria-describedby="launchHint ? 'batch-launch-hint' : undefined"
              :disabled="isLaunchButtonDisabled"
              @click="handleButtonClick"
            >
              <span v-if="isSending" class="btn-spinner" aria-hidden="true"></span>
              {{ buttonLabel }}
            </button>
            <p v-if="launchHint" id="batch-launch-hint" class="launch-hint">{{ launchHint }}</p>

            <button
              type="button"
              class="btn secondary cancel-button"
              :disabled="status !== 'In Progress'"
              @click="cancelBatchWorkflow"
            >
              {{ $t('common.cancel') }}
            </button>

            <button
              type="button"
              class="btn secondary download-button"
              :disabled="status !== 'Batch completed' && status !== 'Batch cancelled'"
              @click="downloadLogs"
            >
              {{ $t('batch_run.download_logs') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Result image preview -->
  <BaseDialog
    :model-value="!!selectedArtifactImage"
    :title="selectedArtifactImage?.name || $t('batch_run.artifact_image')"
    width="min(960px, 95vw)"
    @update:model-value="closeImageModal"
  >
    <img
      v-if="selectedArtifactImage"
      class="preview-image"
      :src="selectedArtifactImage.src"
      :alt="selectedArtifactImage.name"
    />
  </BaseDialog>

  <SettingsModal
    :is-visible="showSettingsModal"
    @update:is-visible="showSettingsModal = $event"
  />

  <!-- Column guide -->
  <BaseDialog
    v-model="showColumnGuideModal"
    :title="$t('batch_run.column_guide_title')"
    width="560px"
  >
    <div class="manual-content">
      <p class="manual-item">{{ $t('batch_run.manual_intro') }}</p>
      <p class="manual-item">
        <code>id</code> - {{ $t('batch_run.manual_id') }}
      </p>
      <p class="manual-item">
        <code>task</code> - {{ $t('batch_run.manual_task') }}
      </p>
      <div class="manual-item">
        <code>vars</code> - {{ $t('batch_run.manual_vars') }}
        <div class="manual-example">
          <pre>{{ JSON.stringify({"LANGUAGE": "vi", "MAX_ITERATIONS": "3"}, null, 2) }}</pre>
        </div>
      </div>
      <div class="manual-item">
        <code>attachments</code> - {{ $t('batch_run.manual_attachments') }}
        <div class="manual-example">
          <pre>{{ JSON.stringify(["C:\\a_sheep.png"], null, 2) }}</pre>
        </div>
      </div>
    </div>
  </BaseDialog>

  <!-- Batch settings -->
  <BaseDialog
    :model-value="isBatchSettingsModalVisible"
    :title="$t('batch_run.batch_settings')"
    width="500px"
    @update:model-value="(open) => { if (!open) cancelBatchSettings() }"
  >
    <div class="settings-item">
      <label class="setting-label" for="batch-max-parallel">{{ $t('batch_run.max_parallel') }}</label>
      <input
        id="batch-max-parallel"
        type="number"
        v-model.number="maxParallel"
        class="input setting-input"
        min="1"
        max="50"
        step="1"
        aria-describedby="batch-max-parallel-desc"
      />
      <p id="batch-max-parallel-desc" class="setting-desc">{{ $t('batch_run.max_parallel_desc') }}</p>
    </div>
    <div class="settings-item">
      <label class="setting-label" for="batch-log-level">{{ $t('batch_run.log_level') }}</label>
      <span class="select-wrap">
        <select id="batch-log-level" v-model="logLevel" class="select" aria-describedby="batch-log-level-desc">
          <option v-for="level in logLevelOptions" :key="level" :value="level">
            {{ level }}
          </option>
        </select>
        <svg class="select-chevron" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6l4 4 4-4" /></svg>
      </span>
      <p id="batch-log-level-desc" class="setting-desc">{{ $t('batch_run.log_level_desc') }}</p>
    </div>
    <template #footer>
      <button type="button" class="btn secondary" @click="cancelBatchSettings">{{ $t('common.cancel') }}</button>
      <button type="button" class="btn primary" @click="saveBatchSettings">{{ $t('common.save') }}</button>
    </template>
  </BaseDialog>
</template>

<script setup>
import { ref, shallowRef, triggerRef, markRaw, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
const { t, te } = useI18n()

// Extract a readable backend error detail (FastAPI `detail` may be a string, an object or a list)
const extractErrorDetail = (result) => {
  const raw = result?.detail ?? result?.error?.message ?? result?.error
  if (raw === undefined || raw === null || raw === '') return ''
  if (typeof raw === 'string') return raw
  if (Array.isArray(raw)) {
    return raw
      .map(item => (typeof item === 'string' ? item : (item?.msg || item?.message || JSON.stringify(item))))
      .join('; ')
  }
  if (typeof raw === 'object') return raw.message || raw.msg || JSON.stringify(raw)
  return String(raw)
}

// Localized message, optionally followed by the backend detail
const withErrorDetail = (message, result) => {
  const detail = extractErrorDetail(result)
  return detail ? t('batch_run.error_with_detail', { message, detail }) : message
}
import { fetchWorkflowsWithDesc, fetchLogsZip, postBatchWorkflow } from '@/api/client.js'
import SettingsModal from '@/components/common/SettingsModal.vue'
import BaseDialog from '@/components/common/BaseDialog.vue'
import { localizedWorkflowDescription } from '@/utils/workflowDescription.js'
import { toast } from '@/utils/toast.js'

const formatLogTimestamp = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  const milliseconds = String(date.getMilliseconds()).padStart(3, '0')
  return `${month}/${day} - ${hours}:${minutes}:${seconds}.${milliseconds}`
}
const router = useRouter()
const route = useRoute()

// Log box state. Entries never change after being added, so the list is shallow:
// pushing a line does not wrap it in a deep proxy (triggerRef notifies the view).
const logMessages = shallowRef([])
const logMessagesRef = ref(null)

// Log message types
const LOG_TYPES = {
  COMPLETED: 'completed',
  FAILED: 'failed',
  DEFAULT: 'default'
}

// Task input state
const taskPrompt = ref('')

// File selector state
const workflowFiles = ref([])
const selectedYamlFile = ref('')
const fileSearchQuery = ref('')
const isFileSearchDirty = ref(false)
const isFileDropdownOpen = ref(false)
const fileSelectorWrapperRef = ref(null)
const fileSelectorInputRef = ref(null)

// Status state
const status = ref('Idle')
const loading = ref(false)

// Internal status value -> i18n key
const STATUS_LABEL_KEYS = {
  'Connecting...': 'launch.status_connecting',
  'Pending launch': 'launch.status_waiting_launch',
  'Launching...': 'launch.status_launching',
  'Failed': 'launch.status_failed',
  'Error': 'launch.status_error',
  'Disconnected': 'launch.status_disconnected',
  'Connection error': 'launch.status_connection_error',
  'Pending file selection': 'batch_run.status_waiting_file'
}

// Computed status from workflow and input file selection
const computedStatus = computed(() => {
  if (loading.value) return t('batch_run.loading')
  if (status.value === 'Pending workflow selection') return t('batch_run.status_waiting_workflow')
  if (!selectedYamlFile.value) return t('batch_run.status_waiting_workflow')
  if (!selectedInputFile.value) return t('batch_run.status_waiting_file')
  
  // Handle specific statuses from logic
  if (status.value === 'Idle') return t('batch_run.status_idle')
  if (status.value === 'In Progress') return t('batch_run.status_in_progress')
  if (status.value === 'Batch completed') return t('batch_run.status_completed')
  if (status.value === 'Batch cancelled') return t('batch_run.status_cancelled')

  // Map other internal status values to localized labels, falling back to the raw value
  const key = STATUS_LABEL_KEYS[status.value]
  return key && te(key) ? t(key) : status.value
})

// Session ID for downloads
let sessionIdToDownload = null

// Input glow state
const shouldGlow = ref(false)
const taskInputRef = ref(null)
const uploadedAttachments = ref([])
const showAttachmentPopover = ref(false)
let attachmentHoverTimeout = null
const selectedArtifactImage = ref(null)

// Input file selection state
const selectedInputFile = ref(null)
const inputFileInputRef = ref(null)

// WebSocket readiness state
const isConnectionReady = ref(false)
const showSettingsModal = ref(false)
const isBatchSettingsModalVisible = ref(false)
const showColumnGuideModal = ref(false)

// Batch settings
const maxParallel = ref(5)
const logLevel = ref('INFO')
const logLevelOptions = ['INFO', 'DEBUG', 'WARNING', 'ERROR', 'CRITICAL']

// View mode
const viewMode = ref('dashboard')

// Dashboard metrics
const totalRowsCount = ref(0)
const completedRowsCount = ref(0)
const successfulTasks = ref(0)
const failedTasks = ref(0)
const batchStartTime = ref(null)
const batchEndTime = ref(null)

// Elapsed-time display. The loop writes the text node directly instead of going
// through reactive state: a reactive per-tick value would re-render the whole
// view (including the full log list) several times a second while a batch runs.
let timerId = null
const TIMER_INTERVAL_MS = 250
const totalTimeEl = ref(null)

const pad2 = (value) => value.toString().padStart(2, '0')
const formatElapsed = (duration) => {
  const hours = Math.floor(duration / (1000 * 60 * 60))
  const minutes = Math.floor((duration % (1000 * 60 * 60)) / (1000 * 60))
  const seconds = Math.floor((duration % (1000 * 60)) / 1000)
  return `${pad2(hours)}:${pad2(minutes)}:${pad2(seconds)}`
}

const renderTotalTime = () => {
  const el = totalTimeEl.value
  if (!el) return
  const text = batchStartTime.value
    ? formatElapsed((batchEndTime.value || Date.now()) - batchStartTime.value)
    : '00:00:00'
  if (el.textContent !== text) el.textContent = text
}

// Timer functions (4 Hz is plenty for a seconds display)
const startTimer = () => {
  if (timerId !== null) return
  renderTotalTime()
  timerId = setInterval(renderTotalTime, TIMER_INTERVAL_MS)
}

const stopTimer = () => {
  if (timerId !== null) {
    clearInterval(timerId)
    timerId = null
  }
  renderTotalTime()
}

// Fill the element when the dashboard (v-if) mounts and when start/end change.
watch([totalTimeEl, batchStartTime, batchEndTime], renderTotalTime, { flush: 'post' })

const completedRows = computed(() => {
  if (totalRowsCount.value === 0) return '-'
  return `${completedRowsCount.value}/${totalRowsCount.value}`
})

const successRate = computed(() => {
  const totalProcessed = successfulTasks.value + failedTasks.value
  if (totalProcessed === 0) return '—'
  const rate = (successfulTasks.value / totalProcessed) * 100
  return `${Math.round(rate)}%`
})

const progressPercentage = computed(() => {
  if (totalRowsCount.value === 0) return 0
  return Math.round((completedRowsCount.value / totalRowsCount.value) * 100)
})

// "n/N rows · k failed" under the progress hero
const progressDetail = computed(() => {
  if (totalRowsCount.value === 0) return ''
  return t('batch_run.progress_detail', {
    done: completedRowsCount.value,
    total: totalRowsCount.value,
    failed: failedTasks.value
  })
})

// WebSocket reference
let ws = null
let sessionId = null

const filteredWorkflowFiles = computed(() => {
  // If the file search box is untouched, return all workflows
  if (!isFileSearchDirty.value) {
    return workflowFiles.value
  }
  const query = fileSearchQuery.value.trim().toLowerCase()
  if (!query) {
    return workflowFiles.value
  }
  return workflowFiles.value.filter((workflow) =>
    workflow.name?.toLowerCase().includes(query)
  )
})

// Button label computed property
const buttonLabel = computed(() => {
  if (status.value === 'Batch completed' || status.value === 'Batch cancelled') {
    return t('batch_run.relaunch')
  }
  return t('batch_run.launch')
})

// A launch request is in flight or the batch is running
const isSending = computed(() => isWorkflowRunning.value || status.value === 'Launching...')

// Computed button state
const isLaunchButtonDisabled = computed(() => {
  if (loading.value) return true
  if (isSending.value) return true
  if (status.value === 'Batch completed' || status.value === 'Batch cancelled') return false
  if (!isConnectionReady.value) return true
  if (!selectedYamlFile.value || !selectedInputFile.value) return true
  return false
})

// Why Launch is disabled (shown under the button so touch users see it too)
const launchHint = computed(() => {
  if (!isLaunchButtonDisabled.value || loading.value || isSending.value) return ''
  if (!selectedYamlFile.value) return t('batch_run.hint_pick_workflow')
  if (!selectedInputFile.value) return t('batch_run.hint_pick_file')
  if (!isConnectionReady.value) return t('batch_run.hint_connecting')
  return ''
})

// Reset the WebSocket connection and related state
const resetConnectionState = ({ closeSocket = true, clearInputFile = true } = {}) => {
  if (closeSocket && ws) {
    try {
      ws.close()
    } catch (closeError) {
      console.warn('Failed to close WebSocket:', closeError)
    }
  }

  ws = null
  sessionId = null
  isConnectionReady.value = false
  shouldGlow.value = false
  isWorkflowRunning.value = false

  // Stop the timer
  stopTimer()

  // Reset metrics
  totalRowsCount.value = 0
  completedRowsCount.value = 0
  successfulTasks.value = 0
  failedTasks.value = 0
  batchStartTime.value = null
  batchEndTime.value = null

  if (attachmentHoverTimeout) {
    clearTimeout(attachmentHoverTimeout)
    attachmentHoverTimeout = null
  }

  if (clearInputFile) {
    removeInputFile()
  }
}

// Button state management
const isWorkflowRunning = ref(false)

// Current workflow YAML content
const workflowYaml = ref({})

// const goBack = () => {
//   router.push('/workflows')
// }

const applyWorkflowFromRoute = () => {
  let workflowParam = route.query?.workflow || route.query?.file || route.query?.name
  if (Array.isArray(workflowParam)) {
    workflowParam = workflowParam[0]
  }
  if (!workflowParam || typeof workflowParam !== 'string') {
    return
  }

  let fileName = workflowParam.trim()
  if (!fileName) {
    return
  }
  if (!fileName.toLowerCase().endsWith('.yaml')) {
    fileName = `${fileName}.yaml`
  }

  selectedYamlFile.value = fileName
  fileSearchQuery.value = fileName
  isFileSearchDirty.value = false
}

// Load workflow list
const loadWorkflows = async () => {
  loading.value = true
  const result = await fetchWorkflowsWithDesc()
  loading.value = false

  if (result.success) {
    workflowFiles.value = result.workflows
    applyWorkflowFromRoute()
  } else {
    console.error('Failed to load workflows:', result.error)
  }
}

const openFileDropdown = () => {
  if (loading.value || isWorkflowRunning.value) {
    return
  }
  isFileDropdownOpen.value = true
}

const handleFileInputFocus = () => {
  isFileSearchDirty.value = false
  openFileDropdown()
  if (fileSearchQuery.value?.trim()) {
    nextTick(() => fileSelectorInputRef.value?.select())
  }
}

const handleFileInputChange = () => {
  if (loading.value || isWorkflowRunning.value) {
    return
  }
  isFileSearchDirty.value = true
  openFileDropdown()
}

const closeFileDropdown = () => {
  isFileDropdownOpen.value = false
}

const selectWorkflow = (fileName) => {
  if (!fileName) {
    return
  }
  selectedYamlFile.value = fileName
  fileSearchQuery.value = fileName
  isFileSearchDirty.value = false
  closeFileDropdown()

  // Avoid focusing on element after selection
  fileSelectorInputRef.value?.blur()

  router.push({
    query: {
      ...route.query,
      workflow: fileName
    }
  })
}

// Keyboard-active option inside the open listbox (-1 = none)
const activeOptionIndex = ref(-1)
const activeOptionId = computed(() =>
  isFileDropdownOpen.value && activeOptionIndex.value >= 0
    ? `batch-workflow-option-${activeOptionIndex.value}`
    : undefined
)

watch([filteredWorkflowFiles, isFileDropdownOpen], () => {
  activeOptionIndex.value = -1
})

const moveActiveOption = (delta) => {
  const count = filteredWorkflowFiles.value.length
  if (!count) return
  const next = activeOptionIndex.value < 0
    ? (delta > 0 ? 0 : count - 1)
    : (activeOptionIndex.value + delta + count) % count
  activeOptionIndex.value = next
  nextTick(() => {
    document.getElementById(`batch-workflow-option-${next}`)?.scrollIntoView({ block: 'nearest' })
  })
}

const handleFileInputKeydown = (event) => {
  const count = filteredWorkflowFiles.value.length
  switch (event.key) {
    case 'ArrowDown':
    case 'ArrowUp':
      event.preventDefault()
      if (!isFileDropdownOpen.value) openFileDropdown()
      else moveActiveOption(event.key === 'ArrowDown' ? 1 : -1)
      break
    case 'Home':
    case 'End':
      if (isFileDropdownOpen.value && count) {
        event.preventDefault()
        activeOptionIndex.value = event.key === 'Home' ? 0 : count - 1
      }
      break
    case 'Escape':
      if (isFileDropdownOpen.value) {
        event.preventDefault()
        closeFileDropdown()
        resetFileSearchQuery()
      }
      break
    case 'Enter': {
      event.preventDefault()
      const option = filteredWorkflowFiles.value[activeOptionIndex.value] || filteredWorkflowFiles.value[0]
      if (option) selectWorkflow(option.name)
      break
    }
    default:
  }
}

const resetFileSearchQuery = () => {
  fileSearchQuery.value = selectedYamlFile.value || ''
  isFileSearchDirty.value = false
}

let fileInputBlurTimeout = null
const handleFileInputBlur = () => {
  if (fileInputBlurTimeout) clearTimeout(fileInputBlurTimeout)
  fileInputBlurTimeout = setTimeout(() => {
    fileInputBlurTimeout = null
    if (!isFileDropdownOpen.value) {
      resetFileSearchQuery()
    }
  }, 120)
}

const handleClickOutside = (event) => {
  if (
    isFileDropdownOpen.value &&
    fileSelectorWrapperRef.value &&
    !fileSelectorWrapperRef.value.contains(event.target)
  ) {
    closeFileDropdown()
    resetFileSearchQuery()
  }
}

// Add a log entry (stable incremental id so v-for keys never shift)
let logMessageSeq = 0
const addLogMessage = (message, type = LOG_TYPES.DEFAULT) => {
  const timestamp = formatLogTimestamp(Date.now())
  logMessages.value.push(markRaw({
    id: ++logMessageSeq,
    timestamp,
    message,
    type
  }))
  triggerRef(logMessages)
}

// Copy / clear the terminal log
const copyLogs = async () => {
  const text = logMessages.value.map((entry) => `${entry.timestamp}  ${entry.message}`).join('\n')
  try {
    await navigator.clipboard.writeText(text)
    toast.success(t('batch_run.logs_copied'))
  } catch (copyError) {
    console.warn('Failed to copy logs:', copyError)
    toast.error(t('batch_run.logs_copy_failed'))
  }
}

const clearLogs = () => {
  logMessages.value = []
}

// Input file selection methods
const handleInputFileButtonClick = () => {
  if (loading.value || isWorkflowRunning.value) {
    return
  }
  inputFileInputRef.value?.click()
}

const onInputFileSelected = (event) => {
  const file = event.target?.files?.[0]
  if (event.target) {
    event.target.value = ''
  }

  if (!file) {
    return
  }

  // Validate file type
  const allowedExtensions = ['.xlsx', '.csv']
  const fileName = file.name.toLowerCase()
  const isValidType = allowedExtensions.some(ext => fileName.endsWith(ext))

  if (!isValidType) {
    toast.warning(t('batch_run.alert_invalid_input_file'))
    return
  }

  selectedInputFile.value = file
}

const removeInputFile = () => {
  selectedInputFile.value = null
  if (inputFileInputRef.value) {
    inputFileInputRef.value.value = ''
  }
}

const unlockBodyScroll = () => {
  if (typeof document !== 'undefined') {
    document.body.style.overflow = ''
  }
}

const closeImageModal = () => {
  if (!selectedArtifactImage.value) {
    return
  }
  selectedArtifactImage.value = null
  unlockBodyScroll()
}

// Show batch settings modal
// Cancel / Esc / backdrop restore the values from when the modal opened; Save keeps them (clamped).
let batchSettingsSnapshot = null
const showBatchSettingsModal = () => {
  batchSettingsSnapshot = { maxParallel: maxParallel.value, logLevel: logLevel.value }
  isBatchSettingsModalVisible.value = true
}
const cancelBatchSettings = () => {
  if (batchSettingsSnapshot) {
    maxParallel.value = batchSettingsSnapshot.maxParallel
    logLevel.value = batchSettingsSnapshot.logLevel
  }
  isBatchSettingsModalVisible.value = false
}
const saveBatchSettings = () => {
  const parsed = Math.round(Number(maxParallel.value))
  maxParallel.value = Number.isFinite(parsed) ? Math.min(50, Math.max(1, parsed)) : 5
  isBatchSettingsModalVisible.value = false
}

// Handle YAML file selection
const handleYAMLSelection = async (fileName) => {
  if (!fileName) {
    workflowYaml.value = {}
    logMessages.value = []

    // Reset metrics
    totalRowsCount.value = 0
    completedRowsCount.value = 0
    successfulTasks.value = 0
    failedTasks.value = 0
    batchStartTime.value = null
    batchEndTime.value = null

    return
  }

  // Clear the log messages
  logMessages.value = []
}

// Handle button clicks
const handleButtonClick = () => {
  if (status.value === 'Batch completed' || status.value === 'Batch cancelled') {
    // If Relaunch, restart the same workflow and re-enter Launch state
    if (!selectedYamlFile.value) {
      toast.warning(t('launch.alert_choose_workflow'))
      return
    }

    if (!selectedInputFile.value) {
      toast.warning(t('batch_run.alert_select_input_file'))
      return
    }

    resetConnectionState()
    status.value = 'Connecting...'
    handleYAMLSelection(selectedYamlFile.value)
    establishWebSocketConnection()
  } else {
    // If Launch, start the workflow
    launchBatchWorkflow()
  }
}

// Establish a WebSocket connection
const establishWebSocketConnection = () => {
  // Reset any previous state before creating a new socket
  resetConnectionState()

  if (!selectedYamlFile.value) {
    return
  }

  const apiBase = import.meta.env.VITE_API_BASE_URL || ''
  // Defaults: same-origin (works with Vite dev proxy)
  const defaultScheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  let scheme = defaultScheme
  let host = window.location.host

  // In production, prefer explicit API base if provided
  if (!import.meta.env.DEV && apiBase) {
    try {
      const api = new URL(apiBase, window.location.origin)
      scheme = api.protocol === 'https:' ? 'wss:' : 'ws:'
      host = api.host
    } catch {
      // keep defaults
    }
  }

  const wsUrl = `${scheme}//${host}/ws`
  const socket = new WebSocket(wsUrl)
  ws = socket

  // Ignore events from stale sockets
  socket.onopen = () => {
    if (ws !== socket) return
    console.log('WebSocket connected')
  }

  socket.onmessage = (event) => {
    // Ignore messages from sockets that are no longer current
    if (ws !== socket) return

    const msg = JSON.parse(event.data)

    if (msg.type === 'connection') {
      sessionId = msg.data?.session_id || null
      console.log('Connected with session: ', sessionId)

      if (!sessionId) {
        status.value = 'Connection error'
        toast.error(t('launch.alert_missing_session'))
        resetConnectionState()
        return
      }

      isConnectionReady.value = true
      shouldGlow.value = true
      status.value = 'Pending launch'

      nextTick(() => {
        taskInputRef.value?.focus()
      })
    } else {
      processBatchMessage(msg)
    }
  }

  // Ignore errors from sockets that are no longer current
  socket.onerror = (error) => {
    if (ws !== socket) return

    console.error('WebSocket error:', error)
    status.value = 'Connection error'
    toast.error(t('launch.alert_ws_error'))
    resetConnectionState({ closeSocket: false })
  }

  socket.onclose = () => {
    // Ignore close events from sockets that are no longer current
    if (ws !== socket) return

    console.log('WebSocket closed')
    if (status.value === 'In Progress') {
      status.value = 'Disconnected'
    } else if (status.value === 'Connecting...' || status.value === 'Pending launch') {
      status.value = 'Disconnected'
    }
    resetConnectionState({ closeSocket: false, clearInputFile: false })
  }
}

// Watch for file selection changes
watch(selectedYamlFile, (newFile) => {
  taskPrompt.value = ''
  fileSearchQuery.value = newFile || ''
  isFileSearchDirty.value = false

  if (!newFile) {
    resetConnectionState()
    status.value = 'Pending file selection'
    handleYAMLSelection(newFile)
    return
  }

  resetConnectionState()
  status.value = 'Connecting...'
  handleYAMLSelection(newFile)
  establishWebSocketConnection()
})

watch(
  () => uploadedAttachments.value.length,
  (length) => {
    if (!length) {
      showAttachmentPopover.value = false
    }
  }
)

// When called from Launch in WorkflowView, auto pass in corresponding workflow
watch(
  () => route.query?.workflow,
  () => {
    applyWorkflowFromRoute()
  }
)

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
  loadWorkflows()
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  if (fileInputBlurTimeout) {
    clearTimeout(fileInputBlurTimeout)
    fileInputBlurTimeout = null
  }
  unlockBodyScroll()
  resetConnectionState()
  stopTimer()
})

// Toggle to dashboard
const switchToDashboard = async () => {
  viewMode.value = 'dashboard'
  await nextTick()
}

const launchBatchWorkflow = async () => {
  if (!selectedYamlFile.value) {
    toast.warning(t('launch.alert_choose_workflow'))
    return
  }

  if (!selectedInputFile.value) {
    toast.warning(t('batch_run.alert_select_input_file'))
    return
  }

  if (
    !ws ||
    !isConnectionReady.value ||
    !sessionId
  ) {
    toast.warning(t('launch.alert_ws_not_ready'))
    return
  }

  shouldGlow.value = false
  status.value = 'Launching...'

  try {
    const result = await postBatchWorkflow({
      file: selectedInputFile.value,
      sessionId: sessionId,
      yamlFile: selectedYamlFile.value,
        maxParallel: maxParallel.value,
      logLevel: logLevel.value
    })

    if (result.success) {
      console.log('Batch workflow launched: ', result)
      status.value = 'In Progress'
      isWorkflowRunning.value = true
    } else {
      console.error('Failed to launch batch workflow:', result)
      status.value = 'Failed'
      toast.error(withErrorDetail(t('batch_run.alert_launch_failed'), result))
      shouldGlow.value = true
      if (isConnectionReady.value) {
        status.value = 'Pending launch'
      }
    }
  } catch (error) {
    console.error('Error calling batch workflow API:', error)
    status.value = 'Error'
    toast.error(withErrorDetail(t('batch_run.alert_launch_api_failed'), { detail: error?.message }))
    shouldGlow.value = true
    if (isConnectionReady.value) {
      status.value = 'Pending launch'
    }
  }
}

// When workflow is finished or cancelled, re-enable glow
watch(status, (newStatus) => {
  if (newStatus === 'Batch completed' || newStatus === 'Batch cancelled') {
    shouldGlow.value = true
  }
})

// Processes different types of messages
const processBatchMessage = async (msg) => {
  // Batch completed
  if (msg.type === 'batch_completed') {
    const message = t('batch_run.log_batch_completed', { succeeded: msg.data?.succeeded ?? 0, failed: msg.data?.failed ?? 0 })
    addLogMessage(message, LOG_TYPES.DEFAULT)

    // Update metrics
    successfulTasks.value = msg.data.succeeded
    failedTasks.value = msg.data.failed
    completedRowsCount.value = msg.data.succeeded + msg.data.failed
    batchEndTime.value = Date.now()

    // Stop the timer
    stopTimer()

    status.value = 'Batch completed'
    isWorkflowRunning.value = false
    sessionIdToDownload = sessionId
  }

  // Handle batch processing messages
  if (msg.type === 'batch_started') {
    const message = t('batch_run.log_batch_started', { total: msg.data?.total ?? 0 })
    addLogMessage(message, LOG_TYPES.DEFAULT)

    // Initialize metrics
    totalRowsCount.value = msg.data.total
    completedRowsCount.value = 0
    successfulTasks.value = 0
    failedTasks.value = 0
    batchStartTime.value = Date.now()
    batchEndTime.value = null

    // Start the timer
    startTimer()
  }

  if (msg.type === 'batch_task_started') {
    const message = t('batch_run.log_task_started', { id: msg.data?.task_id ?? '-', row: msg.data?.row_index ?? '-' })
    addLogMessage(message, LOG_TYPES.DEFAULT)
  }

  if (msg.type === 'batch_task_completed') {
    const message = t('batch_run.log_task_completed', {
      id: msg.data?.task_id ?? '-',
      row: msg.data?.row_index ?? '-',
      duration: msg.data?.duration_ms ?? '-',
      tokens: msg.data?.token_usage?.total_usage?.total_tokens ?? '-'
    })
    addLogMessage(message, LOG_TYPES.COMPLETED)

    // Update metrics
    completedRowsCount.value++
    successfulTasks.value++
  }

  if (msg.type === 'batch_task_failed') {
    const message = t('batch_run.log_task_failed', {
      id: msg.data?.task_id ?? '-',
      row: msg.data?.row_index ?? '-',
      error: extractErrorDetail({ detail: msg.data?.error }) || t('launch.unknown_error')
    })
    addLogMessage(message, LOG_TYPES.FAILED)

    // Update metrics
    completedRowsCount.value++
    failedTasks.value++
  }
}

// Cancel the currently running workflow
const cancelBatchWorkflow = () => {
  if (!isWorkflowRunning.value || !ws) {
    return
  }
  addLogMessage(t('batch_run.status_cancelled'), LOG_TYPES.DEFAULT)

  // Finalize metrics
  batchEndTime.value = Date.now()

  // Stop the timer
  stopTimer()

  status.value = 'Batch cancelled'
  isWorkflowRunning.value = false
  sessionIdToDownload = sessionId

  try {
    ws.close()
  } catch (closeError) {
    console.warn('Failed to close WebSocket:', closeError)
  }
}

// Download logs
const downloadLogs = async () => {
  if (!sessionIdToDownload) {
    return
  }
  try {
    await fetchLogsZip(sessionIdToDownload)
  } catch (error) {
    console.error('Download failed:', error)
    toast.error(t('launch.alert_download_logs_failed'))
  }
}

// Auto-scroll to bottom (coalesced to one scroll per frame when messages arrive in bursts)
let scrollFrame = null
const scrollLogsToBottom = () => {
  if (scrollFrame !== null) return
  scrollFrame = requestAnimationFrame(() => {
    scrollFrame = null
    if (logMessagesRef.value) {
      logMessagesRef.value.scrollTop = logMessagesRef.value.scrollHeight
    }
  })
}

watch(
  () => logMessages.value.length,
  async () => {
    await nextTick()
    scrollLogsToBottom()
  }
)

// The log panel is kept mounted (v-show); re-sync scroll position when it becomes visible
watch(viewMode, async (mode) => {
  if (mode === 'terminal') {
    await nextTick()
    scrollLogsToBottom()
  }
})
</script>
<style scoped>
.launch-view {
  --label-ink: rgb(var(--ink) / 0.68);
  --mono: 'Cascadia Code', 'Cascadia Mono', Consolas, 'SF Mono', Menlo, 'Ubuntu Mono', monospace;
  width: 100%;
  height: 100vh;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  background-color: var(--bg);
  color: var(--fg);
  font-family: 'Inter', sans-serif;
  position: relative;
  overflow: hidden;
}

.launch-bg {
  position: fixed;
  top: -150px;
  left: 0;
  right: 0;
  height: 500px;
  /* Pre-softened radial glows instead of a big blur layer (cheaper to composite). */
  background:
    radial-gradient(ellipse 40% 70% at 18% 45%, var(--success), transparent 72%),
    radial-gradient(ellipse 40% 70% at 50% 45%, var(--accent), transparent 72%),
    radial-gradient(ellipse 40% 70% at 82% 45%, var(--info), transparent 72%);
  opacity: 0.15;
  z-index: 0;
  pointer-events: none;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  height: 48px;
  background-color: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  position: relative;
  z-index: 2;
}

.header h1 {
  margin: 0;
  color: var(--fg);
  font-size: 18px;
  font-weight: 600;
}

.settings-button {
  color: var(--info);
}

.content {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
  padding: 20px;
  gap: 20px;
  position: relative;
  z-index: 1;
}

/* ---------- Left panel ---------- */
.left-panel {
  flex: 3;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
  min-height: 0;
}

.log-box {
  flex: 1;
  min-height: 0;
  background-color: var(--surface);
  border: 1px solid var(--line-3);
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  font-family: var(--mono);
}

.log-toolbar {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  font-family: 'Inter', sans-serif;
}

.log-toolbar .log-tool {
  min-height: 32px;
  padding: 0 10px;
  font-size: var(--fs-xs);
  color: var(--label-ink);
}

.log-toolbar .log-tool:hover:not(:disabled) {
  color: var(--fg);
}



.dashboard-box {
  flex: 1;
  min-height: 0;
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.dashboard-content {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  color: var(--text-2b);
  display: flex;
  flex-direction: column;
  gap: 28px;
  font-size: 14px;
  line-height: 1.4;
}

/* Progress hero */
.progress-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.progress-label {
  font-size: 13px;
  color: var(--label-ink);
  font-weight: 600;
}

.progress-detail {
  font-size: 13px;
  color: var(--label-ink);
  font-variant-numeric: tabular-nums;
}

.progress-row {
  display: flex;
  align-items: center;
  gap: 20px;
}

.progress-bar {
  flex: 1;
  height: 12px;
  background: rgb(var(--ink) / 0.1);
  border-radius: 6px;
  overflow: hidden;
  position: relative;
}

.progress-fill {
  position: relative;
  height: 100%;
  border-radius: 6px;
  background: var(--accent);
  transition: width 0.3s var(--ease-out), background-color 0.3s;
  overflow: hidden;
}

.progress-fill.is-done {
  background: var(--accent-green-2);
}

.progress-fill.is-cancelled {
  background: var(--danger);
}

/* Moving sheen only while a batch is actually running */
.progress-fill.processing::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent 0%, rgb(255 255 255 / 0.5) 50%, transparent 100%);
  transform: translateX(-100%);
  animation: wavePulse 1.8s ease-in-out infinite;
}

.progress-text {
  min-width: 3.4ch;
  text-align: right;
  font-size: 40px;
  line-height: 1;
  font-weight: 700;
  color: var(--fg);
  font-variant-numeric: tabular-nums;
}

/* Metrics */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.metric-card {
  background: rgb(var(--ink) / 0.04);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  transition: border-color 0.3s, box-shadow 0.3s;
}

/* Pulse lives on the status card only, and only while running */
.metric-card.status-active {
  border-color: var(--accent);
  animation: statusPulse 2.4s ease-in-out infinite;
}

.metric-title {
  font-size: var(--fs-xs);
  color: var(--label-ink);
  font-weight: 600;
}

.metric-value {
  font-size: 26px;
  line-height: 1.2;
  font-weight: 700;
  color: var(--fg);
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}

.metric-status {
  font-size: 18px;
  font-weight: 600;
}

.metric-timer {
  font-family: var(--mono);
  letter-spacing: -0.02em;
}

/* ---------- Log lines ---------- */
.log-messages::-webkit-scrollbar { width: 8px; height: 8px; }
.log-messages::-webkit-scrollbar-track { background: transparent; }
.log-messages::-webkit-scrollbar-thumb {
  background-color: rgb(var(--neutral-160) / 0.28);
  border-radius: 8px;
  border: 2px solid transparent;
  background-clip: padding-box;
}
.log-messages::-webkit-scrollbar-thumb:hover { background-color: rgb(var(--neutral-160) / 0.48); }

.log-messages {
  flex: 1;
  min-height: 0;
  padding: 16px 20px;
  overflow-y: auto;
  color: var(--text-2b);
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  line-height: 1.5;
}

.log-message {
  display: flex;
  gap: 12px;
  align-items: baseline;
  white-space: pre-wrap;
  word-break: break-word;
  /* Skip layout/paint for off-screen rows when the log grows large */
  content-visibility: auto;
  contain-intrinsic-size: auto 20px;
}

.log-timestamp {
  flex: none;
  width: 21ch;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.log-text {
  flex: 1;
  min-width: 0;
}

.log-timestamp-completed { color: var(--accent-green-2); }
.log-timestamp-failed { color: var(--danger); }
.log-timestamp-default { color: var(--accent-sky-4); }
.log-text-completed { color: var(--accent-green-2); }
.log-text-failed { color: var(--danger); }

.log-placeholder {
  color: var(--label-ink);
  font-family: 'Inter', sans-serif;
  text-align: center;
  margin-top: 20px;
}

/* ---------- Right panel ---------- */
.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 280px;
  min-height: 0;
  overflow-y: auto;
}

.control-section {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}

.section-label {
  font-size: var(--fs-xs);
  color: var(--label-ink);
  font-weight: 600;
  margin-top: 6px;
}

.field-hint {
  margin: 6px 0 0;
  font-size: var(--fs-xs);
  color: var(--label-ink);
}

.input-file-section { margin-bottom: 4px; }

.input-manual { margin-bottom: 4px; }

.manual-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 0;
  border: none;
  background: transparent;
  font: inherit;
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--label-ink);
  cursor: pointer;
  transition: color 0.2s;
}

.manual-title:hover { color: var(--fg); }

.info-icon { opacity: 0.8; }

/* File picker */
.file-upload-wrapper {
  display: flex;
  align-items: stretch;
  gap: 6px;
}

.hidden-file-input { display: none; }

.file-upload-button {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 0 12px;
  background-color: rgb(var(--ink) / 0.05);
  border: 1px dashed rgb(var(--ink) / 0.3);
  border-radius: 8px;
  color: var(--label-ink);
  font-size: 14px;
  cursor: pointer;
  text-align: left;
  transition: background-color 0.2s, border-color 0.2s, color 0.2s;
}

.file-upload-button svg { flex: none; }

.file-upload-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-upload-button.has-file {
  border-style: solid;
  color: var(--fg);
}

.file-upload-button:hover:not(:disabled) {
  background-color: rgb(var(--ink) / 0.09);
  border-color: rgb(var(--ink) / 0.4);
}

.file-upload-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Workflow combobox */
.select-wrapper,
.custom-file-selector { position: relative; }

.file-selector-input {
  padding-right: 36px;
  cursor: text;
}

.select-arrow {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--label-ink);
  pointer-events: none;
  transition: transform 0.2s var(--ease-out);
}

.select-arrow.open { transform: translateY(-50%) rotate(180deg); }

.file-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin: 4px 0 0;
  list-style: none;
  background-color: var(--surface-3);
  border: 1px solid var(--line-4);
  border-radius: 8px;
  box-shadow: 0 20px 40px -12px rgb(var(--shade) / 0.45);
  max-height: 260px;
  overflow-y: auto;
  z-index: var(--z-dropdown);
  padding: 6px 0;
}

.file-option {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 14px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.file-option.active { background: rgb(var(--ink) / 0.08); }
.file-option.selected .file-name { color: var(--accent); }

.file-name {
  color: var(--fg);
  font-size: 14px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-desc {
  color: var(--label-ink);
  font-size: var(--fs-xs);
}

.file-empty {
  padding: 12px 14px;
  color: var(--label-ink);
  font-size: 13px;
  text-align: center;
}

.file-dropdown-enter-active,
.file-dropdown-leave-active { transition: opacity 0.15s var(--ease-out), transform 0.15s var(--ease-out); }
.file-dropdown-enter-from,
.file-dropdown-leave-to { opacity: 0; transform: translateY(-4px); }

/* View toggle */
.view-toggle {
  display: flex;
  background: rgb(var(--ink) / 0.07);
  padding: 4px;
  border-radius: 8px;
}

.toggle-button {
  flex: 1;
  min-height: 34px;
  padding: 6px;
  border: none;
  background: transparent;
  color: var(--label-ink);
  cursor: pointer;
  border-radius: 6px;
  font-size: 13px;
  transition: background-color 0.2s, color 0.2s;
}

.toggle-button:hover:not(.active) { color: var(--fg); }

.toggle-button.active {
  background: var(--surface-4);
  color: var(--fg);
  font-weight: 600;
  box-shadow: 0 0 0 1px rgb(var(--ink) / 0.12);
}

/* ---------- Actions ---------- */
.button-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 8px;
}

.button-section .launch-button {
  min-height: 48px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  font-size: 16px;
  font-weight: 600;
  transition: transform 0.2s var(--ease-out), box-shadow 0.2s, filter 0.2s;
}

.button-section .launch-button:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 18px -6px rgb(var(--accent-sky-rgb) / 0.55);
}

.button-section .launch-button:disabled {
  opacity: 1;
  background: var(--surface-5);
  border-color: var(--surface-5);
  color: var(--label-ink);
  cursor: not-allowed;
}

/* Ready cue: a short ring pulse (3 times), not an endless loop */
.button-section .launch-button.glow:not(:disabled) {
  animation: glowPulse 2.4s ease-out 3;
}

.button-section .launch-button.is-sending:disabled {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
  cursor: progress;
  opacity: 0.85;
}

.launch-hint {
  margin: -4px 0 0;
  font-size: var(--fs-xs);
  line-height: 1.4;
  color: var(--label-ink);
  text-align: center;
}

.button-section .cancel-button {
  min-height: 44px;
  border-color: var(--danger);
  color: var(--danger);
}

.button-section .cancel-button:hover:not(:disabled) {
  background: color-mix(in srgb, var(--danger) 14%, transparent);
}

.button-section .cancel-button:disabled {
  opacity: 1;
  border-color: var(--border);
  color: var(--fg-subtle);
  cursor: not-allowed;
}

.button-section .download-button {
  min-height: 44px;
}

/* ---------- Dialog contents ---------- */
.preview-image {
  display: block;
  max-width: 100%;
  max-height: 70vh;
  margin: 0 auto;
  border-radius: 6px;
}

.manual-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  font-size: 14px;
  line-height: 1.5;
}

.manual-item {
  margin: 0;
  color: var(--text-2);
}

.manual-item code {
  background-color: rgb(var(--accent-indigo-rgb) / 0.12);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--mono);
  font-size: 12px;
  color: var(--info);
  font-weight: 500;
}

.manual-example { margin-top: 8px; }

.manual-example pre {
  background-color: var(--surface-4);
  border: 1px solid var(--line-3);
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 12px;
  color: var(--text-2);
  font-family: var(--mono);
  overflow-x: auto;
  margin: 0;
}

.settings-item { margin-bottom: 22px; }
.settings-item:last-child { margin-bottom: 0; }

.setting-label {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--fg);
  margin-bottom: 8px;
}

.setting-input { width: 96px; }

.setting-desc {
  margin: 6px 0 0;
  color: var(--label-ink);
  font-size: 13px;
  line-height: 1.4;
}

/* ---------- Keyframes ---------- */
@keyframes glowPulse {
  0% { box-shadow: 0 0 0 0 rgb(var(--accent-sky-rgb) / 0.5); }
  70%, 100% { box-shadow: 0 0 0 8px rgb(var(--accent-sky-rgb) / 0); }
}

@keyframes statusPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgb(var(--accent-sky-rgb) / 0.35); }
  50% { box-shadow: 0 0 0 4px rgb(var(--accent-sky-rgb) / 0); }
}

@keyframes wavePulse {
  0% { transform: translateX(-100%); opacity: 0; }
  50% { opacity: 1; }
  100% { transform: translateX(100%); opacity: 0; }
}

/* ---------- Responsive: 1200 / 980 (stack) / 900 / 640 ---------- */
@media (max-width: 1200px) {
  .content { gap: 16px; padding: 16px; }
  .right-panel { min-width: 260px; }
}

/* Panels stack: controls on top, results below, the page scrolls */
@media (max-width: 980px) {
  .launch-view {
    height: auto;
    min-height: 100vh;
    min-height: 100dvh;
  }

  .content {
    flex-direction: column-reverse;
    overflow: visible;
    padding: 12px 16px 24px;
  }

  .right-panel {
    min-width: 0;
    overflow: visible;
  }

  .left-panel { min-height: 420px; }
}

@media (max-width: 900px) {
  .metric-value { font-size: 24px; }
  .progress-text { font-size: 34px; }
}

@media (max-width: 640px) {
  .content { padding: 12px 12px 20px; }
  .dashboard-content { padding: 16px; gap: 22px; }
  .metrics-grid { grid-template-columns: 1fr; }
  .progress-row { gap: 12px; }
  .progress-text { font-size: 28px; }
  .log-message { flex-direction: column; gap: 0; }
  .log-timestamp { width: auto; }
  .log-toolbar .log-tool { min-height: 40px; }
}

@media (prefers-reduced-motion: reduce) {
  .button-section .launch-button,
  .button-section .launch-button.glow:not(:disabled),
  .progress-fill.processing::before,
  .metric-card.status-active {
    animation: none;
  }
  .select-arrow,
  .progress-fill { transition: none; }
}
</style>

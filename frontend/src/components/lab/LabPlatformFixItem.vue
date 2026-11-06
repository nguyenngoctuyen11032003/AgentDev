<template>
  <li class="pfi" :aria-labelledby="titleId">
    <header class="pfi-head">
      <h4 :id="titleId" class="pfi-branch"><code>{{ current.branch }}</code></h4>
      <span :class="['pfi-badge', verifyTone]">
        <PfStatusIcon :tone="verifyTone" />
        {{ verifyLabel }}
      </span>
    </header>
    <p class="pfi-meta">
      <span v-if="current.head">{{ t('lab.platform_fixes.head', { sha: shortSha(current.head) }) }}</span>
      <span v-if="current.ahead">{{ t('lab.platform_fixes.ahead', { n: current.ahead, base: current.base || 'main' }) }}</span>
      <span v-if="current.dirty_files">{{ t('lab.platform_fixes.dirty', { n: current.dirty_files }) }}</span>
    </p>

    <div v-if="forbidden.length" class="pfi-forbidden" role="group" :aria-label="t('lab.platform_fixes.forbidden_title')">
      <p class="pfi-sub">{{ t('lab.platform_fixes.forbidden_title') }}</p>
      <ul class="pfi-files">
        <li v-for="f in forbidden" :key="f"><code>{{ f }}</code></li>
      </ul>
    </div>

    <details v-if="changed.length" class="pfi-more">
      <summary>{{ t('lab.platform_fixes.changed_files', { n: changed.length }) }}</summary>
      <ul class="pfi-files">
        <li v-for="f in changed" :key="f" :class="{ bad: forbidden.includes(f) }">
          <code>{{ f }}</code>
          <span v-if="forbidden.includes(f)" class="pfi-tag">{{ t('lab.platform_fixes.forbidden_badge') }}</span>
        </li>
      </ul>
    </details>
    <p v-else class="pfi-muted">{{ t('lab.platform_fixes.no_changes') }}</p>

    <div class="pfi-gates">
      <p class="pfi-sub">{{ t('lab.platform_fixes.gates_title') }}</p>
      <ul v-if="gates.length" class="pfi-gate-list">
        <li v-for="g in gates" :key="g.code" class="pfi-gate">
          <div class="pfi-gate-row">
            <PfStatusIcon :tone="statusTone(g.status)" />
            <span class="pfi-gate-name">{{ gateName(g.code) }}</span>
            <span :class="['pfi-gate-status', statusTone(g.status)]">{{ gateStatus(g.status) }}</span>
          </div>
          <p v-if="g.summary" class="pfi-gate-summary">{{ g.summary }}</p>
          <details v-if="g.tail" class="pfi-more pfi-tail">
            <summary>{{ t('lab.platform_fixes.show_output') }}</summary>
            <p v-if="g.command" class="pfi-muted"><code>{{ g.command }}</code></p>
            <pre class="pfi-pre" tabindex="0" :aria-label="`${gateName(g.code)}: ${t('lab.platform_fixes.show_output')}`">{{ g.tail }}</pre>
          </details>
        </li>
      </ul>
      <p v-else class="pfi-muted">{{ t('lab.platform_fixes.no_verify') }}</p>
    </div>

    <details class="pfi-more" @toggle="onReportToggle">
      <summary>{{ t('lab.platform_fixes.report_summary') }}</summary>
      <p v-if="reportLoading" class="pfi-muted" role="status">
        <span class="btn-spinner" aria-hidden="true"></span>
        {{ t('lab.platform_fixes.report_loading') }}
      </p>
      <div v-else-if="reportError" class="pfi-error" role="alert">
        <p>{{ t('lab.platform_fixes.report_failed', { error: reportError }) }}</p>
        <button type="button" class="btn secondary sm" @click="loadReport">{{ t('lab.platform_fixes.report_retry') }}</button>
      </div>
      <pre v-else-if="report" class="pfi-pre" tabindex="0" :aria-label="t('lab.platform_fixes.report_summary')">{{ report }}</pre>
    </details>

    <div v-if="blockers.length" class="pfi-blockers">
      <p class="pfi-sub">{{ t('lab.platform_fixes.blockers_title') }}</p>
      <ul class="pfi-blocker-list">
        <li v-for="code in blockers" :key="code">
          <span class="pfi-blocker-text">{{ blockerText(code) }}</span>
          <span class="pfi-blocker-fix">{{ t('lab.platform_fixes.blocker_fix', { fix: blockerFix(code) }) }}</span>
        </li>
      </ul>
    </div>
    <p v-else-if="mergeable" class="pfi-ready">{{ t('lab.platform_fixes.ready') }}</p>

    <p v-if="actionError" class="pfi-error-text" role="alert">{{ actionError }}</p>

    <div class="pfi-actions">
      <button v-if="verifying" type="button" class="btn secondary sm" :disabled="busy" @click="cancelVerify">
        <span v-if="busy" class="btn-spinner" aria-hidden="true"></span>
        {{ busy ? t('lab.platform_fixes.cancelling') : t('lab.platform_fixes.cancel_verify') }}
      </button>
      <button v-else type="button" class="btn secondary sm" :disabled="busy" @click="verify">
        <span v-if="busy" class="btn-spinner" aria-hidden="true"></span>
        {{ busy ? t('lab.platform_fixes.verify_starting') : t('lab.platform_fixes.verify') }}
      </button>
      <button type="button" class="btn primary sm" aria-haspopup="dialog" :disabled="!mergeable || busy" @click="emit('merge', current)">
        {{ t('lab.platform_fixes.merge') }}
      </button>
      <button type="button" class="btn ghost sm pfi-discard" aria-haspopup="dialog" :disabled="busy" @click="emit('discard', current)">
        {{ t('lab.platform_fixes.discard') }}
      </button>
    </div>
    <span class="sr-only" role="status" aria-live="polite">{{ announce }}</span>
  </li>
</template>

<script setup>
// One platform-fix worktree: changes, last verify (polled while running), short report, merge blockers.
// Merge / discard dialogs live in the parent so their result stays on screen after the item leaves the list.
import { computed, onBeforeUnmount, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { labPlatformFixCancelVerify, labPlatformFixDetail, labPlatformFixVerify } from '@/api/client'
import { labErrorText } from '@/utils/labOutputs.js'
import {
  blockersOf,
  canMerge,
  errorCodeOf,
  gatesOf,
  isVerifying,
  list,
  platformFixErrorText,
  pollDelay,
  shortSha,
  statusTone
} from '@/utils/platformFixes.js'
import PfStatusIcon from './PfStatusIcon.vue'

const props = defineProps({ item: { type: Object, required: true } })
// merge / discard: open the confirmation dialog for this item; refresh: the list is out of date (e.g. 404)
const emit = defineEmits(['merge', 'discard', 'refresh'])

const { t, te } = useI18n()
const titleId = `pfi-${useId()}`

// Newer state than the list gave (verify answers and polled details); dropped when the list brings a newer item.
const live = ref(null)
const current = computed(() => live.value || props.item)
const verifying = computed(() => isVerifying(current.value))
const mergeable = computed(() => canMerge(current.value))
const gates = computed(() => gatesOf(current.value))
const blockers = computed(() => blockersOf(current.value))
const changed = computed(() => list(current.value.changed_files))
const forbidden = computed(() => list(current.value.forbidden_touched))
const verifyTone = computed(() => (current.value.verify ? statusTone(current.value.verify.status) : 'muted'))
const verifyLabel = computed(() => {
  const status = current.value.verify?.status
  const key = `lab.platform_fixes.verify_state.${status}`
  return status && te(key) ? t(key) : t('lab.platform_fixes.no_verify')
})

const gateName = (code) => (te(`lab.platform_fixes.gate.${code}`) ? t(`lab.platform_fixes.gate.${code}`) : code)
const gateStatus = (status) => (te(`lab.platform_fixes.gate_status.${status}`) ? t(`lab.platform_fixes.gate_status.${status}`) : status)
const blockerKey = (code, part) =>
  te(`lab.platform_fixes.blockers.${code}.${part}`) ? `lab.platform_fixes.blockers.${code}.${part}` : `lab.platform_fixes.blockers.unknown.${part}`
const blockerText = (code) => t(blockerKey(code, 'text'), { code })
const blockerFix = (code) => t(blockerKey(code, 'fix'), { code })
const errorText = (error) => platformFixErrorText(error, { t, te, fallback: (e) => labErrorText(e, { t, te }) })

let alive = true
const busy = ref(false)
const actionError = ref('')
const announce = ref('')

// --- Short report: loaded when first opened, refreshed by every polled detail ---
const report = ref('')
const reportLoading = ref(false)
const reportError = ref('')
let reportOpen = false
let reportSeq = 0
async function loadReport() {
  const seq = ++reportSeq
  reportLoading.value = true
  reportError.value = ''
  try {
    const data = await labPlatformFixDetail(props.item.id)
    if (!alive || seq !== reportSeq) return
    report.value = String(data?.report || '')
    applyDetail(data)
  } catch (error) {
    if (alive && seq === reportSeq) reportError.value = errorText(error)
  } finally {
    if (alive && seq === reportSeq) reportLoading.value = false
  }
}
function onReportToggle(event) {
  reportOpen = event.target.open
  if (reportOpen && !report.value && !reportLoading.value) loadReport()
}

// --- Verify polling (backoff; stopped on unmount and when the verify ends) ---
let pollTimer = null
let pollAttempt = 0
let pollSeq = 0
function stopPolling() {
  clearTimeout(pollTimer)
  pollTimer = null
  pollSeq += 1
}
function schedulePoll() {
  clearTimeout(pollTimer)
  if (!alive || !verifying.value) return
  const seq = pollSeq
  pollTimer = setTimeout(() => poll(seq), pollDelay(pollAttempt))
  pollAttempt += 1
}
async function poll(seq) {
  try {
    const data = await labPlatformFixDetail(props.item.id)
    if (!alive || seq !== pollSeq) return
    applyDetail(data)
    if (data?.report) report.value = String(data.report)
  } catch (error) {
    if (!alive || seq !== pollSeq) return
    if (errorCodeOf(error) === 'not_found') {
      emit('refresh')
      return
    }
    // A missed poll is retried with the next (longer) delay.
  }
  schedulePoll()
}

function applyDetail(data) {
  if (!data || typeof data !== 'object' || data.id !== props.item.id) return
  const wasRunning = verifying.value
  const item = { ...data }
  delete item.report
  live.value = item
  if (wasRunning && !isVerifying(item)) {
    const status = item.verify?.status
    if (te(`lab.platform_fixes.announce.${status}`)) announce.value = t(`lab.platform_fixes.announce.${status}`, { branch: item.branch })
  }
}
function applyVerify(verify) {
  if (!verify || typeof verify !== 'object') return
  live.value = { ...current.value, verify }
}

async function verify() {
  if (busy.value) return
  busy.value = true
  actionError.value = ''
  announce.value = ''
  const id = props.item.id
  try {
    const data = await labPlatformFixVerify(id)
    if (!alive || id !== props.item.id) return
    applyVerify(data?.verify)
  } catch (error) {
    if (!alive || id !== props.item.id) return
    const code = errorCodeOf(error)
    // Already running elsewhere (another tab): follow it instead of failing.
    if (code === 'verify_running') applyVerify({ ...(current.value.verify || {}), status: 'running' })
    else actionError.value = errorText(error)
    if (code === 'not_found') emit('refresh')
  } finally {
    if (alive) busy.value = false
  }
  pollAttempt = 0
  stopPolling()
  schedulePoll()
}

async function cancelVerify() {
  if (busy.value) return
  busy.value = true
  actionError.value = ''
  const id = props.item.id
  stopPolling()
  try {
    const data = await labPlatformFixCancelVerify(id)
    if (!alive || id !== props.item.id) return
    applyVerify(data?.verify)
  } catch (error) {
    if (!alive || id !== props.item.id) return
    actionError.value = errorText(error)
    if (['verify_not_running', 'not_found'].includes(errorCodeOf(error))) emit('refresh')
  } finally {
    if (alive) busy.value = false
  }
  schedulePoll()
}

// A newer list item replaces the local copy unless a poll is following a running verify.
watch(
  () => props.item,
  () => {
    if (!pollTimer) live.value = null
    if (reportOpen) loadReport()
  }
)

// Pick up a verify that was already running when the page opened.
if (isVerifying(props.item)) schedulePoll()

onBeforeUnmount(() => {
  alive = false
  stopPolling()
})
</script>

<style scoped>
.pfi { display: grid; gap: 8px; padding: 12px 14px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); min-width: 0; }
.pfi-head { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
.pfi-branch { margin: 0; font-size: 13.5px; font-weight: 650; min-width: 0; overflow-wrap: anywhere; }
.pfi-badge { display: inline-flex; align-items: center; gap: 5px; padding: 2px 9px; border-radius: 999px; font-size: 12px; font-weight: 600; box-shadow: inset 0 0 0 1px var(--line); color: var(--fg-muted); }
.pfi-badge.ok { color: var(--success); }
.pfi-badge.bad { color: var(--danger); }
.pfi-badge.live { color: var(--accent); }
.pfi-meta { display: flex; flex-wrap: wrap; gap: 4px 14px; margin: 0; font-size: 12.5px; color: var(--fg-muted); font-variant-numeric: tabular-nums; }
.pfi-sub { margin: 0; font-size: 12.5px; font-weight: 650; }
.pfi-muted { margin: 0; font-size: 12.5px; color: var(--fg-muted); }
.pfi-forbidden { display: grid; gap: 4px; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--danger); background: color-mix(in srgb, var(--danger) 8%, transparent); }
.pfi-forbidden .pfi-sub { color: var(--danger); }
.pfi-files { margin: 0; padding-left: 18px; display: grid; gap: 2px; font-size: 12.5px; }
.pfi-files code { overflow-wrap: anywhere; }
.pfi-files li.bad code { color: var(--danger); font-weight: 600; }
.pfi-tag { margin-left: 6px; padding: 0 6px; border-radius: 999px; font-size: 11.5px; font-weight: 600; color: var(--danger); box-shadow: inset 0 0 0 1px var(--danger); }
.pfi-more summary { cursor: pointer; width: fit-content; font-size: 12.5px; font-weight: 600; border-radius: 4px; }
.pfi-more summary:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.pfi-more[open] > summary { margin-bottom: 4px; }
.pfi-gates { display: grid; gap: 4px; }
.pfi-gate-list { margin: 0; padding: 0; list-style: none; display: grid; gap: 4px; }
.pfi-gate { display: grid; gap: 2px; min-width: 0; }
.pfi-gate-row { display: flex; align-items: center; gap: 8px; font-size: 13px; min-width: 0; }
.pfi-gate-name { min-width: 0; overflow-wrap: anywhere; }
.pfi-gate-status { margin-left: auto; flex: none; font-size: 12px; font-weight: 600; color: var(--fg-muted); }
.pfi-gate-status.ok { color: var(--success); }
.pfi-gate-status.bad { color: var(--danger); }
.pfi-gate-summary { margin: 0 0 0 24px; font-size: 12.5px; color: var(--fg-muted); overflow-wrap: anywhere; }
.pfi-tail { margin-left: 24px; }
.pfi-pre {
  max-height: 260px;
  overflow: auto;
  margin: 4px 0 0;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--tint-2, var(--surface-raised));
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.pfi-pre:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.pfi-blockers { display: grid; gap: 4px; padding: 8px 10px; border-radius: 8px; background: color-mix(in srgb, var(--warn) 14%, transparent); }
.pfi-blocker-list { margin: 0; padding-left: 18px; display: grid; gap: 6px; font-size: 13px; }
.pfi-blocker-list li { display: grid; gap: 1px; }
.pfi-blocker-text { font-weight: 600; }
.pfi-blocker-fix { color: var(--fg-muted); overflow-wrap: anywhere; }
.pfi-ready { margin: 0; font-size: 13px; font-weight: 600; color: var(--success); }
.pfi-error { display: grid; gap: 6px; justify-items: start; font-size: 12.5px; }
.pfi-error p { margin: 0; }
.pfi-error-text { margin: 0; font-size: 13px; color: var(--danger); font-weight: 600; overflow-wrap: anywhere; }
.pfi-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.pfi-discard { color: var(--danger); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
@media (max-width: 720px) {
  .btn.sm { min-height: 44px; }
  .pfi-more summary { display: flex; align-items: center; min-height: 44px; }
  .pfi-actions .btn { flex: 1 1 100%; }
  .pfi-gate-summary, .pfi-tail { margin-left: 0; }
}
</style>

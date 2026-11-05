<template>
  <aside v-if="visible" :class="['cleanup', { ready: passed }]" role="status" aria-live="polite">
    <svg class="cl-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6M14 11v6" /></svg>
    <div class="cl-text">
      <strong>
        {{ passed
          ? tr('lab.cleanup.title_passed', 'Kiểm định đạt. Dọn {n} lượt thử cũ ({size}) của quy trình này?', params)
          : tr('lab.cleanup.title', 'Có {n} lượt thử cũ ({size}) của quy trình này. Dọn bớt cho nhẹ máy?', params) }}
      </strong>
      <span>
        {{ tr('lab.cleanup.keeps', 'Vẫn giữ: sản phẩm của lần vừa chạy{baseline}, điểm và lịch sử mọi lần.', {
          baseline: hint.baseline_job && hint.baseline_job !== jobId ? tr('lab.cleanup.keeps_baseline', ' và của lần đạt gần nhất') : ''
        }) }}
      </span>
    </div>
    <div class="cl-actions">
      <button type="button" class="btn primary sm" :disabled="busy" @click="clean">
        <span v-if="busy" class="btn-spinner" aria-hidden="true"></span>
        {{ tr('lab.cleanup.confirm', 'Dọn ngay') }}
      </button>
      <button type="button" class="btn ghost sm" :disabled="busy" @click="later">{{ tr('lab.cleanup.later', 'Để sau') }}</button>
      <button type="button" class="link-btn" :disabled="busy" @click="never">{{ tr('lab.cleanup.never', 'Không hỏi lại') }}</button>
    </div>
  </aside>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { labCleanupSuggestion, labCleanupWorkflow } from '@/api/client'
import { formatBytes } from '@/utils/labOutputs.js'
import { toast } from '@/utils/toast.js'

// Shown once an evaluation has finished, only when this workflow's older products have piled up
// (the backend decides: >= 500 MB or >= 20 old runs). Asking right after the result is the moment the user
// knows what to keep; a passing result is the natural point to let go of the attempts before it.
const props = defineProps({
  workflow: { type: String, default: '' },
  jobId: { type: String, default: '' },
  finished: { type: Boolean, default: false },
  passed: { type: Boolean, default: false }
})
const emit = defineEmits(['cleaned'])

const { t, te, locale } = useI18n()
const tr = (key, fallback, params) =>
  te(key) ? t(key, params) : String(fallback).replace(/\{(\w+)\}/g, (_, k) => params?.[k] ?? '')

const NEVER_KEY = 'agentdev.lab.cleanup.never'
const LATER_KEY = 'agentdev.lab.cleanup.later'
const hint = reactive({ suggest: false, reclaimable_runs: 0, reclaimable_bytes: 0, baseline_job: '' })
const dismissed = ref(false)
const busy = ref(false)
let asked = ''

const params = computed(() => ({ n: hint.reclaimable_runs, size: formatBytes(hint.reclaimable_bytes, locale.value) }))
const visible = computed(() => props.finished && hint.suggest && !dismissed.value)

function readFlag(storage, key) {
  try {
    return storage.getItem(key)
  } catch {
    return null
  }
}
function writeFlag(storage, key, value) {
  try {
    storage.setItem(key, value)
  } catch {
    // storage unavailable: the prompt may simply come back
  }
}

async function check() {
  const key = `${props.workflow}|${props.jobId}`
  if (!props.finished || !props.workflow || !props.jobId || asked === key) return
  asked = key
  dismissed.value = readFlag(localStorage, NEVER_KEY) === '1' || readFlag(sessionStorage, LATER_KEY) === props.jobId
  hint.suggest = false
  if (dismissed.value) return
  try {
    const data = await labCleanupSuggestion(props.workflow, props.jobId)
    if (asked === key) Object.assign(hint, data)
  } catch {
    // advisory only
  }
}
watch(() => [props.workflow, props.jobId, props.finished], check, { immediate: true })

async function clean() {
  busy.value = true
  try {
    const result = await labCleanupWorkflow(props.workflow, props.jobId)
    toast.success(tr('lab.cleanup.done', 'Đã dọn {n} lượt, giải phóng {size}', {
      n: result.deleted, size: formatBytes(result.freed_bytes, locale.value)
    }))
    dismissed.value = true
    emit('cleaned')
  } catch (error) {
    toast.error(error?.message || tr('lab.cleanup.failed', 'Không dọn được kết quả cũ'))
  } finally {
    busy.value = false
  }
}
function later() {
  writeFlag(sessionStorage, LATER_KEY, props.jobId)
  dismissed.value = true
}
function never() {
  writeFlag(localStorage, NEVER_KEY, '1')
  dismissed.value = true
  toast.info(tr('lab.cleanup.never_note', 'Sẽ không hỏi nữa. Vẫn dọn được bằng nút "Dọn kết quả cũ" cuối trang.'))
}
</script>

<style scoped>
.cleanup { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 16px; margin: 0 0 16px; padding: 14px 16px; border-radius: 12px; background: var(--surface-raised); box-shadow: inset 0 0 0 1px var(--line); }
.cleanup.ready { background: color-mix(in srgb, var(--accent) 8%, var(--surface-raised)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 35%, var(--line)); }
.cl-icon { flex: none; color: var(--accent); }
.cl-text { display: flex; flex: 1 1 300px; flex-direction: column; gap: 3px; min-width: 0; font-size: 13px; line-height: 1.5; color: var(--fg-muted); }
.cl-text strong { font-size: 14px; color: var(--fg); }
.cl-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.link-btn { padding: 4px 6px; border: 0; background: none; font: inherit; font-size: 12.5px; color: var(--fg-muted); text-decoration: underline; text-underline-offset: 3px; cursor: pointer; }
.link-btn:hover { color: var(--fg); }
.link-btn:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; border-radius: 4px; }
</style>

<template>
  <details v-if="jobs.length" class="history" :open="expanded" @toggle="expanded = $event.target.open">
    <summary>
      <svg class="h-icon" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5M12 7v5l3 2" /></svg>
      <span class="h-title">{{ tr('lab.history.title', 'Lịch sử thử nghiệm') }}</span>
      <span class="h-count">{{ jobs.length }}</span>
      <span class="h-hint">{{ tr('lab.history.hint', 'Mở lại một lần kiểm định để xem điểm và sản phẩm đã tạo') }}</span>
      <svg class="h-chevron" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
    </summary>
    <ul class="h-list">
      <li v-for="item in jobs" :key="item.id">
        <button
          type="button"
          :class="['h-row', { current: item.id === currentId }]"
          :aria-current="item.id === currentId ? 'true' : undefined"
          @click="emit('open', item.id)"
        >
          <span :class="['h-dot', tone(item)]" aria-hidden="true"></span>
          <span class="h-when">{{ when(item.started_at) }}</span>
          <span class="h-status">{{ statusText(item) }}</span>
          <span class="h-meta">
            <template v-if="item.pass_rate != null">{{ tr('lab.history.pass_rate', 'Đạt {n}%', { n: Math.round(item.pass_rate * 100) }) }} · </template>
            {{ tr('lab.history.runs', '{n} lượt', { n: item.done ?? 0 }) }}
            <template v-if="item.cost_usd"> · ${{ Number(item.cost_usd).toFixed(2) }}</template>
          </span>
          <span class="h-open">{{ item.id === currentId ? tr('lab.history.viewing', 'Đang xem') : tr('lab.history.open', 'Xem') }}</span>
        </button>
      </li>
    </ul>
  </details>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { labJobs } from '@/api/client'

// Past evaluations of one workflow (stored on the server), so results and products stay reachable
// after a reload or from another tab. Bump refreshKey to re-read the list (e.g. when a job finishes).
const props = defineProps({
  workflow: { type: String, default: '' },
  currentId: { type: String, default: '' },
  refreshKey: { type: Number, default: 0 }
})
const emit = defineEmits(['open'])

const { t, te, locale } = useI18n()
const tr = (key, fallback, params) =>
  te(key) ? t(key, params) : String(fallback).replace(/\{(\w+)\}/g, (_, k) => params?.[k] ?? '')

const jobs = ref([])
const expanded = ref(false)
let requestNo = 0

async function load() {
  const name = props.workflow
  const mine = ++requestNo
  if (!name) {
    jobs.value = []
    return
  }
  try {
    const data = await labJobs(name)
    if (mine === requestNo) jobs.value = Array.isArray(data?.jobs) ? data.jobs : []
  } catch {
    if (mine === requestNo) jobs.value = []
  }
}

watch(() => [props.workflow, props.refreshKey], load, { immediate: true })

function when(seconds) {
  if (!seconds) return '—'
  return new Date(seconds * 1000).toLocaleString(locale.value, { dateStyle: 'short', timeStyle: 'short' })
}
function statusText(item) {
  if (item.status === 'completed' && item.verdict) {
    return item.verdict === 'ready' ? tr('lab.history.ready', 'Đạt') : tr('lab.history.not_ready', 'Chưa đạt')
  }
  return te(`lab.job_status.${item.status}`) ? t(`lab.job_status.${item.status}`) : item.status
}
function tone(item) {
  if (item.status === 'running' || item.status === 'queued') return 'live'
  if (item.status === 'completed') return item.verdict === 'ready' ? 'ok' : 'warn'
  return item.status === 'error' ? 'bad' : 'muted'
}
</script>

<style scoped>
.history { margin-top: 16px; border-radius: 12px; box-shadow: inset 0 0 0 1px var(--line); background: var(--surface); }
.history summary { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; padding: 12px 14px; cursor: pointer; list-style: none; font-size: 13.5px; color: var(--fg); border-radius: 12px; }
.history summary::-webkit-details-marker { display: none; }
.history summary:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.h-icon { flex: none; color: var(--fg-muted); }
.h-title { font-weight: 600; }
.h-count { min-width: 22px; padding: 1px 7px; border-radius: 999px; font-size: 12px; text-align: center; color: var(--fg-muted); box-shadow: inset 0 0 0 1px var(--line); }
.h-hint { flex: 1 1 220px; min-width: 0; font-size: 12.5px; color: var(--fg-muted); }
.h-chevron { flex: none; margin-left: auto; color: var(--fg-muted); transition: transform 0.18s ease; }
.history[open] .h-chevron { transform: rotate(180deg); }
.h-list { margin: 0; padding: 0 8px 8px; list-style: none; max-height: 320px; overflow-y: auto; }
.h-row { display: grid; grid-template-columns: auto minmax(110px, auto) minmax(70px, auto) 1fr auto; align-items: center; gap: 12px; width: 100%; padding: 9px 10px; border: 0; border-radius: 8px; background: none; font: inherit; font-size: 13px; text-align: left; color: var(--fg); cursor: pointer; }
.h-row:hover { background: var(--surface-raised); }
.h-row:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.h-row.current { background: var(--surface-raised); box-shadow: inset 2px 0 0 var(--accent); }
.h-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--fg-muted); }
.h-dot.ok { background: var(--ok, #16a34a); }
.h-dot.warn { background: var(--warn); }
.h-dot.bad { background: var(--danger); }
.h-dot.live { background: var(--accent); }
.h-when { font-variant-numeric: tabular-nums; color: var(--fg-muted); }
.h-status { font-weight: 600; }
.h-meta { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--fg-muted); font-variant-numeric: tabular-nums; }
.h-open { font-size: 12.5px; font-weight: 600; color: var(--accent); }
.h-row.current .h-open { color: var(--fg-muted); }
@media (max-width: 640px) {
  .h-row { grid-template-columns: auto 1fr auto; }
  .h-status, .h-meta { grid-column: 2 / 4; }
  .h-open { display: none; }
}
@media (prefers-reduced-motion: reduce) { .h-chevron { transition: none; } }
</style>

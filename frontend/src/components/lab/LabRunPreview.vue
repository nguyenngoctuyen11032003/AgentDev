<template>
  <section class="preview" :aria-label="tr('lab.outputs.preview_title', 'Chạy thử')">
    <header class="pv-bar">
      <span :class="['pv-status', tone]" role="status">
        <span v-if="busy" class="pv-pulse" aria-hidden="true"></span>
        <span v-else class="pv-dot" aria-hidden="true"></span>
        {{ statusLabel }}
      </span>
      <a
        v-if="state.status === 'running' && frameUrl"
        class="pv-url"
        :href="frameUrl"
        target="_blank"
        rel="noopener noreferrer"
        :title="tr('lab.outputs.new_tab', 'Mở trong tab mới')"
      >{{ displayUrl }}</a>
      <span class="pv-spacer"></span>

      <div v-if="state.status === 'running'" class="pv-devices" role="group" :aria-label="tr('lab.outputs.device_label', 'Kích thước khung')">
        <button
          v-for="d in DEVICES"
          :key="d.id"
          type="button"
          :class="['pv-device', { on: device === d.id }]"
          :aria-pressed="device === d.id"
          :title="tr(`lab.outputs.device.${d.id}`, d.label)"
          :aria-label="tr(`lab.outputs.device.${d.id}`, d.label)"
          @click="device = d.id"
        >
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path v-for="(p, pi) in d.icon" :key="pi" :d="p" /></svg>
        </button>
      </div>

      <template v-if="state.status === 'running'">
        <button type="button" class="btn ghost sm icon-only" :title="tr('lab.outputs.preview_reload', 'Tải lại')" :aria-label="tr('lab.outputs.preview_reload', 'Tải lại')" @click="frameKey++">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.6-6.4L21 8" /><path d="M21 3v5h-5" /></svg>
        </button>
        <a class="btn ghost sm icon-only" :href="frameUrl" target="_blank" rel="noopener noreferrer" :title="tr('lab.outputs.new_tab', 'Mở trong tab mới')" :aria-label="tr('lab.outputs.new_tab', 'Mở trong tab mới')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></svg>
        </a>
      </template>
      <button
        v-if="['failed', 'stopped', 'idle'].includes(state.status)"
        type="button"
        class="btn secondary sm"
        :disabled="acting"
        @click="start"
      >
        <span v-if="acting" class="btn-spinner" aria-hidden="true"></span>
        <svg v-else viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
        {{ tr('lab.outputs.preview_restart', 'Chạy lại') }}
      </button>
      <button
        v-if="busy || state.status === 'running'"
        type="button"
        class="btn secondary sm danger-outline"
        :disabled="acting"
        @click="stop"
      >
        <span v-if="acting" class="btn-spinner" aria-hidden="true"></span>
        <svg v-else viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
        {{ tr('lab.outputs.preview_stop', 'Dừng') }}
      </button>
      <button type="button" class="btn ghost sm icon-only" :title="tr('lab.outputs.preview_hide', 'Ẩn khung chạy thử')" :aria-label="tr('lab.outputs.preview_hide', 'Ẩn khung chạy thử')" @click="emit('close')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
      </button>
    </header>

    <div v-if="state.status === 'running' && frameUrl && state.frameable === false" class="pv-external">
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="10" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
      <div class="pv-external-text">
        <strong>{{ tr('lab.outputs.preview_no_frame_title', 'App đang chạy, nhưng không cho hiển thị trong khung') }}</strong>
        <span>{{ tr('lab.outputs.preview_no_frame_hint', 'App tự bật chế độ chống nhúng vào trang khác (X-Frame-Options), đúng chuẩn bảo mật. Mở nó trong tab mới để xem và bấm thử.') }}</span>
      </div>
      <a class="btn primary sm" :href="frameUrl" target="_blank" rel="noopener noreferrer">
        {{ tr('lab.outputs.preview_open_tab', 'Mở app trong tab mới') }}
      </a>
    </div>
    <div v-else-if="state.status === 'running' && frameUrl" class="pv-stage">
      <iframe
        :key="frameKey"
        :src="frameUrl"
        :class="['pv-frame', device]"
        :title="tr('lab.outputs.preview_frame', 'Bản chạy thử của sản phẩm')"
        sandbox="allow-scripts allow-forms allow-popups"
        referrerpolicy="no-referrer"
      ></iframe>
    </div>
    <div v-else-if="busy" class="pv-wait">
      <span class="btn-spinner" aria-hidden="true"></span>
      <div>
        <strong>{{ statusLabel }}…</strong>
        <span>{{ tr('lab.outputs.preview_wait', 'Lần đầu có thể mất vài phút để cài thư viện.') }}</span>
      </div>
    </div>
    <p v-else-if="state.status === 'failed' || error" class="pv-error" role="alert">
      <strong>{{ tr('lab.outputs.preview_error', 'Không chạy thử được') }}</strong>
      <span v-if="state.error || state.error_code || error">{{ state.status === 'failed' && (state.error || state.error_code) ? stateErrorText : error }}</span>
    </p>
    <p v-else-if="state.status === 'stopped'" class="pv-note">{{ tr('lab.outputs.preview_stopped_note', 'Bản chạy thử đã dừng. Bấm "Chạy lại" để chạy tiếp.') }}</p>

    <details v-if="state.log_tail" class="pv-log" :open="state.status === 'failed'">
      <summary>{{ tr('lab.outputs.preview_log', 'Nhật ký') }}</summary>
      <pre ref="logEl">{{ state.log_tail }}</pre>
    </details>
    <p v-if="state.status === 'running' && state.kind !== 'static'" class="pv-foot">{{ tr('lab.outputs.preview_idle_note', 'Bản chạy thử tự dừng sau 30 phút không dùng.') }}</p>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { labPreviewHeartbeat, labPreviewStart, labPreviewStatus, labPreviewStop } from '@/api/client'
import { labErrorText } from '@/utils/labOutputs.js'

const props = defineProps({
  jobId: { type: String, required: true },
  // run_id of the run (position for jobs stored before run ids existed)
  run: { type: [String, Number], required: true },
  // true: start the preview right away (user pressed "Chạy thử"); false: only show the current state
  autostart: { type: Boolean, default: false }
})
const emit = defineEmits(['close', 'status'])

const { t, te } = useI18n()
const tr = (key, fallback, params) =>
  te(key) ? t(key, params) : String(fallback).replace(/\{(\w+)\}/g, (_, k) => params?.[k] ?? '')

const DEVICES = [
  { id: 'desktop', label: 'Máy tính', icon: ['M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z', 'M8 21h8M12 17v4'] },
  { id: 'tablet', label: 'Máy tính bảng', icon: ['M6 3h12a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z', 'M11 18h2'] },
  { id: 'mobile', label: 'Điện thoại', icon: ['M8 3h8a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z', 'M11 18h2'] }
]
const POLL_MS = 1500
// While the preview is on screen the server is told it is still watched, so it is not stopped as idle.
const HEARTBEAT_MS = 60_000

const EMPTY = { status: 'idle', url: null, port: null, kind: null, log_tail: '', error: null, error_code: null, error_params: null, frameable: null }
const state = reactive({ ...EMPTY })
const error = ref('')
const acting = ref(false)
const frameKey = ref(0)
const device = ref('desktop')
const logEl = ref(null)
let timer = null
let alive = true

const busy = computed(() => ['installing', 'starting'].includes(state.status))
const tone = computed(() =>
  ({ running: 'ok', failed: 'bad', installing: 'busy', starting: 'busy' })[state.status] || 'idle'
)
const errText = (err) => labErrorText(err, { t, te })
// A failed preview carries error_code/error_params: show it in the UI language.
const stateErrorText = computed(() => labErrorText(state, { t, te }))
const statusLabel = computed(() => tr(`lab.outputs.preview_status.${state.status}`, state.status))
// Static sites come back as a relative /api/... URL: the app's own origin serves (or proxies) it.
const frameUrl = computed(() => state.url || '')
const displayUrl = computed(() => {
  const url = frameUrl.value
  if (!url) return ''
  return url.startsWith('/') ? `${window.location.host}${url}` : url.replace(/^https?:\/\//, '')
})

function apply(data) {
  Object.assign(state, EMPTY, data || {})
  emit('status', state.status)
  schedule()
}
function schedule() {
  clearTimeout(timer)
  timer = null
  if (alive && busy.value) timer = setTimeout(refresh, POLL_MS)
}
async function refresh() {
  timer = null
  try {
    apply(await labPreviewStatus(props.jobId, props.run))
    error.value = ''
  } catch (err) {
    if (!alive) return
    error.value = errText(err)
    // Keep trying while it is starting: one dropped request should not end the wait.
    schedule()
  }
}
async function start() {
  if (acting.value) return
  acting.value = true
  error.value = ''
  try {
    apply(await labPreviewStart(props.jobId, props.run))
    frameKey.value += 1
  } catch (err) {
    error.value = errText(err)
    state.status = 'failed'
  } finally {
    acting.value = false
  }
}
async function stop() {
  if (acting.value) return
  acting.value = true
  try {
    apply(await labPreviewStop(props.jobId, props.run))
    if (!['stopped', 'idle'].includes(state.status)) state.status = 'stopped'
  } catch (err) {
    error.value = errText(err)
  } finally {
    acting.value = false
  }
}

// Keep the newest log lines in view when the log is open.
watch(() => state.log_tail, () => nextTick(() => {
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
}))

// Heartbeat: every minute while the preview is open and the tab is visible, and right away when the
// tab comes back. Hidden tabs and closed previews send nothing, so the server can stop idle ones.
let beatTimer = null
const watching = () => alive && document.visibilityState === 'visible' && ['installing', 'starting', 'running'].includes(state.status)
async function beat() {
  if (!watching()) return
  try {
    const res = await labPreviewHeartbeat(props.jobId, props.run)
    // The server already stopped it (idle, crash): show the real state instead of a dead frame.
    if (alive && res && res.alive === false && state.status === 'running') refresh()
  } catch {
    // a missed beat is harmless: the next one (or the status poll) catches up
  }
}
function startBeats() {
  clearInterval(beatTimer)
  beatTimer = setInterval(beat, HEARTBEAT_MS)
}
function onVisibility() {
  if (document.visibilityState === 'visible') {
    beat()
    startBeats()
  } else {
    clearInterval(beatTimer)
    beatTimer = null
  }
}

onMounted(() => {
  if (props.autostart) start()
  else refresh()
  document.addEventListener('visibilitychange', onVisibility)
  if (document.visibilityState === 'visible') startBeats()
})
// Closing the panel unmounts this component: beats stop, and the server stops the idle preview later.
onBeforeUnmount(() => {
  alive = false
  clearTimeout(timer)
  clearInterval(beatTimer)
  document.removeEventListener('visibilitychange', onVisibility)
})
defineExpose({ start })
</script>

<style scoped>
.preview { margin-top: 12px; border-radius: 12px; background: var(--surface); box-shadow: inset 0 0 0 1px var(--line-strong); overflow: hidden; }
.pv-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; padding: 8px 8px 8px 12px; border-bottom: 1px solid var(--line); background: var(--tint); }
.pv-status { --c: var(--fg-muted); display: inline-flex; align-items: center; gap: 7px; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 650; color: var(--c); background: color-mix(in srgb, var(--c) 13%, transparent); white-space: nowrap; }
.pv-status.ok { --c: var(--success); }
.pv-status.bad { --c: var(--danger); }
.pv-status.busy { --c: var(--accent); }
.pv-dot, .pv-pulse { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.pv-pulse { animation: pv-pulse 1.4s ease-in-out infinite; }
@keyframes pv-pulse { 50% { opacity: 0.35; transform: scale(0.8); } }
.pv-url { min-width: 0; max-width: 40ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: var(--fg-muted); font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; text-decoration: none; }
.pv-url:hover { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; }
.pv-spacer { flex: 1; }
.pv-devices { display: inline-flex; padding: 2px; border-radius: 9px; background: var(--tint-2); }
.pv-device { display: grid; place-items: center; width: 32px; height: 28px; border: 0; border-radius: 7px; background: transparent; color: var(--fg-muted); cursor: pointer; transition: background-color 0.15s ease, color 0.15s ease; }
.pv-device:hover { color: var(--fg); }
.pv-device.on { background: var(--surface); color: var(--fg); box-shadow: 0 1px 2px rgb(0 0 0 / 0.12); }
.pv-device:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }
.btn.danger-outline { color: var(--danger); border-color: color-mix(in srgb, var(--danger) 55%, transparent); }
.btn.danger-outline:hover { background: color-mix(in srgb, var(--danger) 10%, transparent); color: var(--danger); }

.pv-external { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; padding: 22px 18px; color: var(--fg-muted); background: var(--tint-2); }
.pv-external > svg { flex: none; color: var(--accent); }
.pv-external-text { display: flex; flex: 1 1 260px; flex-direction: column; gap: 3px; min-width: 0; font-size: 13px; line-height: 1.5; }
.pv-external-text strong { font-size: 14px; color: var(--fg); }
.pv-stage { display: flex; justify-content: center; padding: 0; background: var(--tint-2); }
.pv-frame { display: block; width: 100%; height: min(70vh, 640px); border: 0; background: #fff; transition: width 0.25s var(--ease-out, ease); }
.pv-frame.tablet { width: min(100%, 820px); box-shadow: 0 0 0 1px var(--line-strong); }
.pv-frame.mobile { width: min(100%, 390px); box-shadow: 0 0 0 1px var(--line-strong); }
.pv-wait { display: flex; gap: 12px; align-items: center; padding: 28px 18px; font-size: 13px; color: var(--fg-muted); }
.pv-wait div { display: flex; flex-direction: column; gap: 2px; }
.pv-wait strong { color: var(--fg); font-size: 14px; }
.pv-wait .btn-spinner { color: var(--accent); }
.pv-error { display: flex; flex-direction: column; gap: 2px; margin: 0; padding: 14px 16px; font-size: 13px; line-height: 1.5; color: var(--fg-muted); background: color-mix(in srgb, var(--danger) 7%, transparent); overflow-wrap: anywhere; }
.pv-error strong { color: var(--danger); }
.pv-note, .pv-foot { margin: 0; padding: 12px 16px; font-size: 12.5px; color: var(--fg-muted); }
.pv-foot { padding: 8px 12px; border-top: 1px solid var(--line); }
.pv-log { border-top: 1px solid var(--line); }
.pv-log summary { padding: 8px 12px; font-size: 12.5px; font-weight: 600; color: var(--fg-muted); cursor: pointer; }
.pv-log summary:hover { color: var(--fg); }
.pv-log summary:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.pv-log pre { margin: 0; max-height: 240px; overflow: auto; padding: 10px 12px; font-size: 11.5px; line-height: 1.55; white-space: pre-wrap; word-break: break-word; color: var(--fg); background: var(--tint); font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; }
@media (prefers-reduced-motion: reduce) {
  .pv-pulse { animation: none; }
  .pv-frame, .pv-device { transition: none; }
}
</style>

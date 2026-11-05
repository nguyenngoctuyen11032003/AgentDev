<template>
  <section v-if="cards.length || emptyCount" class="products" aria-labelledby="lab-products-title">
    <header class="pr-head">
      <h3 id="lab-products-title" class="pr-title">{{ tr('lab.products.title', 'Sản phẩm của lần kiểm định') }}</h3>
      <p class="pr-sub">
        <template v-if="cards.length">{{ tr('lab.products.count', '{n} lượt có sản phẩm', { n: cards.length }) }}</template>
        <template v-if="cards.length && emptyCount"> · </template>
        <template v-if="emptyCount">{{ tr('lab.products.empty_runs', '{n} lượt không tạo file', { n: emptyCount }) }}</template>
      </p>
    </header>

    <ul v-if="cards.length" class="pr-grid">
      <li v-for="c in cards" :key="c.run" :class="['pr-card', c.type, { live: stateOf(c.run) === 'running' }]">
        <div class="pr-top">
          <span :class="['pr-icon', c.type]" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path v-for="(p, pi) in ICONS[c.type]" :key="pi" :d="p" /></svg>
          </span>
          <div class="pr-id">
            <span class="pr-type">{{ typeLabel(c.type) }}</span>
            <strong class="pr-name" :title="c.name">{{ c.name }}</strong>
          </div>
          <span :class="['pr-pill', c.status]">{{ te(`lab.run_status.${c.status}`) ? t(`lab.run_status.${c.status}`) : c.status }}</span>
        </div>

        <p class="pr-meta">{{ c.meta }}</p>
        <p v-if="c.inferred" class="pr-inferred" :title="tr('lab.products.inferred_hint', 'Bản cũ chưa ghi thư mục cho lượt lỗi hoặc hết giờ: thư mục được ghép với lượt này theo thời gian chạy.')">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
          {{ tr('lab.products.inferred', 'Ghép theo thời gian chạy') }}
        </p>

        <!-- Live state of the preview: announced, since starting an app can take minutes -->
        <div class="pr-live" role="status">
          <div v-if="stateOf(c.run) === 'running' && previews[c.run]?.url" class="pr-open">
            <a class="pr-link" :href="previews[c.run].url" target="_blank" rel="noopener noreferrer">
              <span class="pr-link-text">
                <span class="pr-link-label">{{ tr('lab.products.open_web', 'Mở web') }}</span>
                <span class="pr-link-url">{{ displayUrl(previews[c.run].url) }}</span>
              </span>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17 17 7M8 7h9v9" /></svg>
              <span class="sr-only">({{ tr('lab.products.new_tab', 'mở trong tab mới') }})</span>
            </a>
          </div>
          <div v-else-if="isBusy(c.run)" class="pr-wait">
            <span class="btn-spinner" aria-hidden="true"></span>
            <span>
              <strong>{{ tr(`lab.outputs.preview_status.${stateOf(c.run)}`, stateOf(c.run) === 'installing' ? 'Đang cài thư viện' : 'Đang khởi động') }}…</strong>
              {{ tr('lab.products.wait_hint', 'Lần đầu có thể mất vài phút.') }}
            </span>
          </div>
          <p v-else-if="stateOf(c.run) === 'failed'" class="pr-error">
            <strong>{{ tr('lab.products.preview_failed', 'Không chạy thử được.') }}</strong>
            {{ previews[c.run]?.error || tr('lab.products.preview_failed_hint', 'Xem nhật ký trong phần file của lượt này.') }}
          </p>
        </div>

        <div class="pr-actions">
          <template v-if="c.type === 'site'">
            <a class="btn primary sm" :href="siteHref(c)" target="_blank" rel="noopener noreferrer">
              {{ tr('lab.products.open_site', 'Mở trang') }}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17 17 7M8 7h9v9" /></svg>
            </a>
          </template>
          <template v-else-if="c.type === 'webapp'">
            <button v-if="stateOf(c.run) === 'running'" type="button" class="btn secondary sm" @click="emit('show', c.run)">
              {{ tr('lab.products.view_in_lab', 'Xem trong Lab') }}
            </button>
            <button v-else-if="!isBusy(c.run)" type="button" class="btn primary sm" :disabled="acting.has(c.run)" @click="start(c.run)">
              <span v-if="acting.has(c.run)" class="btn-spinner" aria-hidden="true"></span>
              <svg v-else viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
              {{ stateOf(c.run) === 'failed' ? tr('lab.products.retry', 'Thử lại') : tr('lab.products.run', 'Chạy thử') }}
            </button>
          </template>
          <button type="button" class="btn ghost sm" @click="emit('show', c.run)">
            {{ tr('lab.products.view_files', 'Xem file') }}
          </button>
          <button
            v-if="c.type === 'webapp' && (isBusy(c.run) || stateOf(c.run) === 'running')"
            type="button"
            class="btn ghost sm pr-stop"
            :disabled="acting.has(c.run)"
            :aria-label="tr('lab.products.stop_label', 'Dừng bản chạy thử của {name}', { name: c.name })"
            @click="stop(c.run)"
          >
            {{ tr('lab.products.stop', 'Dừng') }}
          </button>
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { labPreviewStart, labPreviewStatus, labPreviewStop, labRunSiteUrl } from '@/api/client'
import { formatBytes } from '@/utils/labOutputs.js'
import { TYPE_ORDER, displayUrl, productType, stackOf } from '@/utils/labProducts.js'

// The "what did this evaluation make" overview: one card per run that left files, with the shortest way to
// look at it (open the site, run the app and open its address, or jump to the files in the run below).
const props = defineProps({
  jobId: { type: String, required: true },
  // GET /api/lab/jobs/{id}/products -> runs
  runs: { type: Array, default: () => [] },
  // (scenario index) -> display name, the same labels as the run list
  scenarioLabel: { type: Function, required: true },
  showAttempt: { type: Boolean, default: false }
})
const emit = defineEmits(['show'])

const { t, te, locale } = useI18n()
const tr = (key, fallback, params) =>
  te(key) ? t(key, params) : String(fallback).replace(/\{(\w+)\}/g, (_, k) => params?.[k] ?? '')

const ICONS = {
  webapp: ['M4 4h16a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z', 'M3 9h18', 'M6.5 6.5h.01M9 6.5h.01', 'm10 13-2 2 2 2M14 13l2 2-2 2'],
  site: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z', 'M3.6 9h16.8M3.6 15h16.8', 'M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18'],
  media: ['M4 4h16a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z', 'm10 9 5 3-5 3V9Z'],
  docs: ['M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z', 'M14 3v5h5', 'M9 13h6M9 17h4'],
  code: ['m8 8-4 4 4 4M16 8l4 4-4 4', 'm14 5-4 14'],
  files: ['M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z']
}
const TYPE_FALLBACK = { webapp: 'Web app', site: 'Trang web', media: 'Video/ảnh', docs: 'Tài liệu', code: 'Mã nguồn', files: 'Tệp' }
const typeLabel = (type) => tr(`lab.products.type.${type}`, TYPE_FALLBACK[type])

const cards = computed(() =>
  props.runs
    .map((entry) => ({ entry, kind: productType(entry) }))
    .filter(({ kind }) => kind)
    .map(({ entry, kind }) => ({
      run: entry.run,
      type: kind.type,
      status: entry.status,
      inferred: !!entry.inferred,
      entry: entry.project?.entry || '',
      name: props.showAttempt
        ? `${props.scenarioLabel(entry.scenario)} · ${t('lab.attempt', { n: entry.repeat })}`
        : props.scenarioLabel(entry.scenario),
      meta: [
        kind.type === 'webapp' ? stackOf(entry.project) : '',
        tr('lab.products.files', '{n} file', { n: entry.file_count }),
        formatBytes(entry.total_bytes, locale.value)
      ].filter(Boolean).join(' · ')
    }))
    .sort((a, b) => TYPE_ORDER[a.type] - TYPE_ORDER[b.type] || a.run - b.run)
)
// Finished runs that left nothing to look at (a run still in progress may yet write files).
const emptyCount = computed(() => props.runs.filter((r) => !productType(r) && r.status !== 'running').length)

const siteHref = (c) => labRunSiteUrl(props.jobId, c.run, c.entry)

// ------------------------------------------------------------------ previews
const POLL_MS = 1500
const previews = reactive({})
const acting = reactive(new Set())
const timers = new Map()
let alive = true

const stateOf = (run) => previews[run]?.status || 'idle'
const isBusy = (run) => ['installing', 'starting'].includes(stateOf(run))

function setState(run, data) {
  previews[run] = { status: data?.status || 'idle', url: data?.url || null, error: data?.error || null }
  clearTimeout(timers.get(run))
  timers.delete(run)
  if (alive && isBusy(run)) timers.set(run, setTimeout(() => poll(run), POLL_MS))
}
const message = (err) => err?.detail || err?.message || String(err)

async function poll(run) {
  const id = props.jobId
  try {
    const data = await labPreviewStatus(id, run)
    if (alive && id === props.jobId) setState(run, data)
  } catch {
    // One dropped request should not end the wait: try again.
    if (alive && id === props.jobId) setState(run, previews[run])
  }
}
async function start(run) {
  if (acting.has(run)) return
  const id = props.jobId
  acting.add(run)
  try {
    const data = await labPreviewStart(id, run)
    if (id === props.jobId) setState(run, data)
  } catch (err) {
    if (id === props.jobId) setState(run, { status: 'failed', error: message(err) })
  } finally {
    acting.delete(run)
  }
}
async function stop(run) {
  if (acting.has(run)) return
  const id = props.jobId
  acting.add(run)
  try {
    await labPreviewStop(id, run)
    if (id === props.jobId) setState(run, { status: 'stopped' })
  } catch (err) {
    if (id === props.jobId) setState(run, { status: 'failed', error: message(err) })
  } finally {
    acting.delete(run)
  }
}

function clearAll() {
  for (const timer of timers.values()) clearTimeout(timer)
  timers.clear()
  for (const key of Object.keys(previews)) delete previews[key]
}
watch(() => props.jobId, clearAll)
// Previews already running (started earlier, here or in a run below) come with the product list.
watch(
  () => props.runs,
  (runs) => {
    for (const entry of runs) {
      const run = entry.run
      if (acting.has(run) || timers.has(run)) continue // a start or a poll of ours is under way
      if (entry.preview) setState(run, entry.preview)
      else if (['running', 'installing', 'starting'].includes(stateOf(run))) setState(run, { status: 'stopped' })
    }
  },
  { immediate: true }
)
onBeforeUnmount(() => {
  alive = false
  for (const timer of timers.values()) clearTimeout(timer)
})
</script>

<style scoped>
.products { margin: 0 0 16px; }
.pr-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px; margin-bottom: 10px; }
.pr-title { margin: 0; font-size: 14px; font-weight: 650; color: var(--fg); }
.pr-sub { margin: 0; font-size: 12.5px; color: var(--fg-muted); }

.pr-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 290px), 1fr)); gap: 10px; margin: 0; padding: 0; list-style: none; }
.pr-card {
  display: flex; flex-direction: column; gap: 8px; min-width: 0; padding: 14px 14px 12px; border-radius: 12px;
  background: var(--surface); box-shadow: inset 0 0 0 1px var(--line);
  transition: box-shadow 0.18s ease;
}
.pr-card.webapp, .pr-card.site { background: var(--tint); }
.pr-card.live { box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--success) 45%, transparent); }

.pr-top { display: flex; gap: 10px; align-items: flex-start; }
.pr-icon {
  --c: var(--accent-indigo-rgb);
  display: grid; flex: none; place-items: center; width: 34px; height: 34px; border-radius: 10px;
  color: rgb(var(--c)); background: rgb(var(--c) / 0.12); box-shadow: inset 0 0 0 1px rgb(var(--c) / 0.22);
}
.pr-icon.webapp, .pr-icon.site { --c: var(--accent-sky-rgb); }
.pr-icon.media { --c: var(--accent-mint-rgb); }
.pr-icon.code, .pr-icon.files { color: var(--fg-muted); background: var(--tint-2); box-shadow: inset 0 0 0 1px var(--line); }
.pr-id { display: flex; flex: 1; flex-direction: column; gap: 1px; min-width: 0; }
.pr-type { font-size: 12px; font-weight: 650; color: var(--fg-muted); }
.pr-name { display: -webkit-box; overflow: hidden; font-size: 14px; font-weight: 650; line-height: 1.35; color: var(--fg); -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow-wrap: anywhere; }
.pr-pill {
  --tone: var(--fg-muted);
  flex: none; padding: 2px 9px; border-radius: 999px; font-size: 11px; font-weight: 650;
  color: var(--tone); background: color-mix(in srgb, var(--tone) 14%, transparent);
}
.pr-pill.passed { --tone: var(--success); }
.pr-pill.failed, .pr-pill.error { --tone: var(--danger); }
.pr-pill.running { --tone: var(--accent); }

.pr-meta { margin: 0; font-size: 12.5px; color: var(--fg-muted); overflow-wrap: anywhere; }
.pr-inferred { display: inline-flex; align-items: center; gap: 5px; align-self: flex-start; margin: 0; font-size: 12px; color: var(--fg-muted); cursor: help; text-decoration: underline dotted; text-underline-offset: 3px; }
.pr-inferred svg { flex: none; }

.pr-live:empty { display: none; }
.pr-link {
  display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 10px; text-decoration: none;
  color: var(--fg); background: color-mix(in srgb, var(--success) 9%, var(--surface));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--success) 40%, transparent);
  transition: background-color 0.15s ease, box-shadow 0.15s ease;
}
.pr-link:hover { background: color-mix(in srgb, var(--success) 15%, var(--surface)); }
.pr-link:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.pr-link > svg { flex: none; margin-left: auto; color: var(--success); }
.pr-link-text { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.pr-link-label { font-size: 14px; font-weight: 700; }
.pr-link-url { overflow: hidden; font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; font-size: 12.5px; color: var(--fg-muted); text-overflow: ellipsis; white-space: nowrap; }
.pr-wait { display: flex; gap: 10px; align-items: center; padding: 10px 12px; border-radius: 10px; font-size: 12.5px; line-height: 1.45; color: var(--fg-muted); background: var(--tint-2); }
.pr-wait strong { color: var(--fg); }
.pr-wait .btn-spinner { flex: none; color: var(--accent); }
.pr-error { margin: 0; padding: 8px 10px; border-radius: 9px; font-size: 12.5px; line-height: 1.5; color: var(--fg-muted); background: color-mix(in srgb, var(--danger) 8%, transparent); overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; }
.pr-error strong { color: var(--danger); }

.pr-actions { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: auto; padding-top: 2px; }
.pr-stop { margin-left: auto; color: var(--fg-muted); }
.pr-stop:hover:not(:disabled) { color: var(--danger); }
.sr-only { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }

@media (max-width: 720px) {
  .pr-actions .btn { min-height: 44px; }
}
@media (prefers-reduced-motion: reduce) {
  .pr-card, .pr-link { transition: none; }
}
</style>

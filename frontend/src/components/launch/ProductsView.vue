<template>
  <div class="products">
    <!-- Where the files are: the opened project or the session's own folder -->
    <div class="pr-bar">
      <span class="pr-where" :class="location?.kind">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
        {{ location?.kind === 'project' ? tr('launch.products.where_project', 'Thư mục dự án') : tr('launch.products.where_session', 'Thư mục của phiên') }}
      </span>
      <code v-if="location?.path" class="pr-path" :title="location.path">{{ location.path }}</code>
      <span class="pr-spacer"></span>
      <span v-if="refreshedAt" class="pr-time">{{ tr('launch.products.updated', 'Cập nhật {time}', { time: clock(refreshedAt) }) }}</span>
      <button
        type="button"
        class="btn ghost sm icon-only"
        :disabled="!sessionId || refreshing"
        :title="tr('launch.products.refresh', 'Tải lại danh sách file')"
        :aria-label="tr('launch.products.refresh', 'Tải lại danh sách file')"
        @click="refresh"
      >
        <span v-if="refreshing" class="btn-spinner" aria-hidden="true"></span>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.6-6.4L21 8" /><path d="M21 3v5h-5" /></svg>
      </button>
    </div>

    <div v-if="!sessionId" class="pr-empty">
      <strong>{{ tr('launch.products.no_session_title', 'Chưa có phiên làm việc') }}</strong>
      <span>{{ tr('launch.products.no_session_hint', 'Giao việc cho nhóm trong khung chat. Mã nguồn, trang web, tài liệu nhóm làm ra sẽ hiện ở đây để bạn xem và chạy thử.') }}</span>
    </div>
    <template v-else>
      <GitChangesPanel ref="changesRef" :session-id="sessionId" :refresh-key="refreshKey" :visible="visible" />
      <LabRunOutputs ref="outputsRef" class="pr-outputs" :source="source" />
    </template>
  </div>
</template>

<script setup>
// "Sản phẩm" view of the Run page: browse what the team wrote for this session and try it
// ("Chạy thử"), with the Lab's file browser and app runner pointed at the session's output folder.
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import GitChangesPanel from '@/components/launch/GitChangesPanel.vue'
import LabRunOutputs from '@/components/lab/LabRunOutputs.vue'
import { fetchOutputLocation } from '@/api/client.js'
import { sessionOutputSource } from '@/utils/outputSources.js'

const props = defineProps({
  sessionId: { type: String, default: '' },
  // Bumped by the page when the files may have changed (a turn ended, a project was opened)
  refreshKey: { type: Number, default: 0 },
  visible: { type: Boolean, default: false },
  // Bumped when "Chạy thử" was pressed elsewhere on the page: start the app as soon as the view is there
  autostartKey: { type: Number, default: 0 }
})

const { t, te, locale } = useI18n()
const tr = (key, fallback, params) =>
  te(key) ? t(key, params) : String(fallback).replace(/\{(\w+)\}/g, (_, k) => params?.[k] ?? '')
const clock = (ms) => new Date(ms).toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' })

const source = computed(() => (props.sessionId ? sessionOutputSource(props.sessionId) : null))
const outputsRef = ref(null)
const changesRef = ref(null)
const location = ref(null)
const refreshing = ref(false)
const refreshedAt = ref(0)
let stale = false
let token = 0

async function loadLocation() {
  const id = ++token
  if (!props.sessionId) {
    location.value = null
    return
  }
  try {
    const result = await fetchOutputLocation(props.sessionId)
    if (id === token) location.value = result
  } catch {
    // the browser below shows its own error
  }
}

async function refresh() {
  if (!props.sessionId || refreshing.value) return
  refreshing.value = true
  stale = false
  try {
    await Promise.all([loadLocation(), outputsRef.value?.reload?.(), changesRef.value?.reload?.()])
    refreshedAt.value = Date.now()
  } finally {
    refreshing.value = false
  }
}

watch(() => props.sessionId, () => {
  stale = false
  refreshedAt.value = props.sessionId ? Date.now() : 0
  loadLocation()
}, { immediate: true })
// Files change while the view is hidden: reload once it is shown again, not on every turn
watch(() => props.refreshKey, () => {
  if (props.visible) refresh()
  else stale = true
})
watch(() => props.visible, (shown) => {
  if (shown && stale) refresh()
})
watch(() => props.autostartKey, (key) => {
  if (key > 0) nextTick(() => outputsRef.value?.openPreview?.(true))
}, { immediate: true })
</script>

<style scoped>
.products {
  /* The Lab's surface tokens, which its file browser and app runner are drawn with */
  --line: rgb(var(--ink) / 0.08);
  --line-strong: rgb(var(--ink) / 0.14);
  --tint: rgb(var(--ink) / 0.035);
  --tint-2: rgb(var(--ink) / 0.06);
  font-variant-numeric: tabular-nums;
  height: 100%;
  box-sizing: border-box;
  overflow-y: auto;
  padding: 16px 16px 24px calc(var(--inset-left, 0px) + 34px);
  display: flex;
  flex-direction: column;
  gap: 12px;
  color: var(--fg);
  scrollbar-width: thin;
  transition: padding-left 0.25s var(--ease-out);
}
.products > * { flex-shrink: 0; }
.pr-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; min-width: 0; }
.pr-where { --c: var(--accent-sky-rgb); display: inline-flex; flex: none; align-items: center; gap: 6px; padding: 3px 10px 3px 8px; border-radius: 999px; font-size: 12px; font-weight: 650; color: rgb(var(--c)); background: rgb(var(--c) / 0.12); }
.pr-where.project { --c: var(--accent-mint-rgb); }
.pr-path { flex: 0 1 auto; min-width: 0; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: var(--fg-muted); font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; }
.pr-spacer { flex: 1; }
.pr-time { font-size: 12px; color: var(--fg-muted); font-variant-numeric: tabular-nums; }
.pr-outputs { margin: 0; }
.pr-empty { display: flex; flex-direction: column; gap: 4px; max-width: 62ch; padding: 28px 22px; border-radius: 12px; background: var(--tint); box-shadow: inset 0 0 0 1px var(--line); font-size: 13px; line-height: 1.55; color: var(--fg-muted); }
.pr-empty strong { font-size: 14.5px; color: var(--fg); }
@media (max-width: 899.98px) {
  .products { padding-left: 16px; }
}
@media (prefers-reduced-motion: reduce) {
  .products { transition: none; }
}
</style>

<template>
  <section class="gc" :aria-label="t('launch.products.changes.title')" data-testid="git-changes">
    <header class="gc-head">
      <h3 class="gc-title">{{ t('launch.products.changes.title') }}</h3>
      <span v-if="view === PANEL_VIEW.READY" class="gc-count">
        {{ t('launch.products.changes.turn', { n: result.turn }) }} · {{ t('launch.products.changes.summary', { n: result.files.length }) }}
      </span>
      <span class="gc-spacer"></span>
      <template v-if="view === PANEL_VIEW.READY">
        <button type="button" class="btn secondary sm" :disabled="busy || !undoable" data-testid="git-undo" @click="undoAll">
          <span v-if="acting === 'undo'" class="btn-spinner" aria-hidden="true"></span>
          {{ acting === 'undo' ? t('launch.products.changes.undoing') : t('launch.products.changes.undo') }}
        </button>
        <button type="button" class="btn ghost sm" :disabled="busy" data-testid="git-keep-branch" :title="t('launch.products.changes.keep_branch_hint')" @click="keepBranch">
          {{ t('launch.products.changes.keep_branch') }}
        </button>
      </template>
    </header>

    <!-- Always in the DOM so a screen reader announces the outcome of an undo -->
    <p class="gc-live" :class="`is-${notice.tone}`" role="status" aria-live="polite" data-testid="git-notice">{{ notice.text }}</p>
    <ul v-if="notice.details.length" class="gc-problems" data-testid="git-problems">
      <li v-for="line in notice.details" :key="line">{{ line }}</li>
    </ul>

    <p v-if="view === PANEL_VIEW.LOADING" class="gc-state" data-testid="git-loading">
      <span class="btn-spinner" aria-hidden="true"></span>{{ t('launch.products.changes.loading') }}
    </p>
    <div v-else-if="view === PANEL_VIEW.ERROR" class="gc-state is-error" role="alert" data-testid="git-error">
      <strong>{{ t('launch.products.changes.error_title') }}</strong>
      <span>{{ errorText }}</span>
      <span>{{ t('launch.products.changes.error_hint') }}</span>
      <button type="button" class="btn secondary sm" @click="reload">{{ t('launch.products.changes.retry') }}</button>
    </div>
    <p v-else-if="view === PANEL_VIEW.RUNNING" class="gc-state" data-testid="git-running">{{ t('launch.products.changes.running') }}</p>
    <p v-else-if="view === PANEL_VIEW.UNAVAILABLE" class="gc-state" data-testid="git-unavailable">{{ unavailableText }}</p>
    <p v-else-if="view === PANEL_VIEW.EMPTY" class="gc-state" data-testid="git-empty">{{ t('launch.products.changes.empty') }}</p>

    <div v-else class="gc-body">
      <ul class="gc-files" :aria-label="t('launch.products.changes.list_label')">
        <li v-for="file in result.files" :key="file.path" class="gc-row" :class="{ active: file.path === selected }">
          <button type="button" class="gc-pick" :aria-pressed="file.path === selected" :title="file.path" @click="selected = file.path">
            <span class="gc-kind" :class="`k-${file.change}`">{{ t(`launch.products.changes.change_${file.change}`) }}</span>
            <span class="gc-name"><span class="gc-dir">{{ splitPath(file.path).dir }}</span>{{ splitPath(file.path).name }}</span>
          </button>
          <span v-if="file.state === FILE_STATE.REVERTED" class="gc-badge ok">{{ t('launch.products.changes.state_reverted') }}</span>
          <span v-else-if="file.state === FILE_STATE.CONFLICT" class="gc-badge warn">{{ t('launch.products.changes.state_conflict') }}</span>
          <button v-else type="button" class="btn ghost sm" :disabled="busy" @click="undoFile(file)">{{ t('launch.products.changes.undo_file') }}</button>
        </li>
      </ul>
      <p v-if="result.truncated" class="gc-more">{{ t('launch.products.changes.more', { n: result.files.length, total: result.total }) }}</p>

      <div v-if="current" class="gc-diff" :aria-label="t('launch.products.changes.diff_label', { path: current.path })" role="group">
        <p v-if="current.binary" class="gc-note">{{ t('launch.products.changes.diff_binary') }}</p>
        <p v-else-if="!lines.length" class="gc-note">{{ t('launch.products.changes.diff_none') }}</p>
        <pre v-else class="gc-pre" tabindex="0"><span v-for="(line, i) in lines" :key="i" class="dl" :class="`t-${line.type}`">{{ line.text || ' ' }}</span></pre>
        <p v-if="current.truncated" class="gc-note">{{ t('launch.products.changes.diff_truncated') }}</p>
      </div>
    </div>
  </section>
</template>

<script setup>
// "Thay đổi" of the Run page's Sản phẩm tab: files the latest run turn edited in a git workspace (hidden checkpoint),
// their diff, and an undo that never overwrites what the user edited afterwards. Logic lives in utils/gitChanges.js.
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { sessionChanges, sessionChangesKeepBranch, sessionChangesUndo } from '@/api/client.js'
import { confirmDialog } from '@/utils/confirm.js'
import {
  canUndo,
  CHANGE_STATUS,
  defaultSelection,
  diffLines,
  FILE_STATE,
  PANEL_VIEW,
  panelView,
  splitPath,
  summarizeUndo
} from '@/utils/gitChanges.js'

const props = defineProps({
  sessionId: { type: String, default: '' },
  // Bumped by the page when a turn ended
  refreshKey: { type: Number, default: 0 },
  visible: { type: Boolean, default: false }
})

const { t } = useI18n()
const result = ref(null)
const loading = ref(false)
const error = ref(null)
const selected = ref('')
const acting = ref('') // '' | 'undo' | 'branch'
const notice = reactive({ tone: 'info', text: '', details: [] })
let token = 0
let stale = true
let alive = true

const view = computed(() => panelView({ loading: loading.value, error: error.value, result: result.value }))
const busy = computed(() => Boolean(acting.value) || loading.value)
const undoable = computed(() => canUndo(result.value?.files))
const current = computed(() => (result.value?.files || []).find((f) => f.path === selected.value) || null)
const lines = computed(() => diffLines(current.value?.diff))
const errorText = computed(() => error.value?.message || result.value?.message || '')
const unavailableText = computed(() => {
  const status = result.value?.status
  if (status === CHANGE_STATUS.NOT_GIT) return t('launch.products.changes.not_git')
  if (status === CHANGE_STATUS.DISABLED) return t('launch.products.changes.disabled')
  return t('launch.products.changes.no_checkpoint')
})

function say(tone, text, details = []) {
  notice.tone = tone
  notice.text = text
  notice.details = details
}

async function reload({ keepNotice = false } = {}) {
  const id = ++token
  if (!props.sessionId) {
    result.value = null
    error.value = null
    loading.value = false
    return
  }
  stale = false
  loading.value = true
  error.value = null
  if (!keepNotice) say('info', '')
  try {
    const data = await sessionChanges(props.sessionId)
    if (!alive || id !== token) return
    result.value = data
    if (!(data.files || []).some((f) => f.path === selected.value)) selected.value = defaultSelection(data.files)
  } catch (err) {
    if (!alive || id !== token) return
    result.value = null
    error.value = err instanceof Error ? err : new Error(String(err))
  } finally {
    if (id === token) loading.value = false
  }
}

function undoNotice(response) {
  const sum = summarizeUndo(response)
  const key = sum.tone === 'success' ? 'undo_done' : sum.done ? 'undo_partial' : 'undo_none'
  const text = t(`launch.products.changes.${key}`, { restored: sum.restored, removed: sum.removed, conflicts: sum.conflicts.length })
  const details = [
    ...sum.conflicts.map((c) => t('launch.products.changes.conflict_line', { path: c.path })),
    ...sum.errors.map((e) => t('launch.products.changes.error_line', { path: e.path, message: e.message }))
  ]
  say(sum.tone, text, details)
}

async function runUndo(paths, confirmCopy) {
  if (!props.sessionId || busy.value) return
  const ok = await confirmDialog({ ...confirmCopy, tone: 'danger' })
  if (!ok) return
  acting.value = 'undo'
  try {
    const response = await sessionChangesUndo(props.sessionId, paths)
    undoNotice(response)
  } catch (err) {
    say('error', t('launch.products.changes.action_failed', { message: err?.message || '' }), [t('launch.products.changes.error_hint')])
  } finally {
    acting.value = ''
  }
  await reload({ keepNotice: true })
}

const undoAll = () =>
  runUndo(null, {
    title: t('launch.products.changes.confirm_title'),
    message: t('launch.products.changes.confirm_message', { n: result.value?.counts?.pending ?? 0 }),
    confirmText: t('launch.products.changes.confirm_ok')
  })

const undoFile = (file) =>
  runUndo([file.path], {
    title: t('launch.products.changes.confirm_file_title'),
    message: t('launch.products.changes.confirm_file_message', { path: file.path }),
    confirmText: t('launch.products.changes.confirm_ok')
  })

async function keepBranch() {
  if (!props.sessionId || busy.value) return
  acting.value = 'branch'
  try {
    const response = await sessionChangesKeepBranch(props.sessionId)
    say('success', t('launch.products.changes.branch_done', { branch: response.branch }))
  } catch (err) {
    say('error', t('launch.products.changes.action_failed', { message: err?.message || '' }), [t('launch.products.changes.error_hint')])
  } finally {
    acting.value = ''
  }
}

watch(() => props.sessionId, () => {
  result.value = null
  selected.value = ''
  say('info', '')
  stale = true
  if (props.visible) reload()
}, { immediate: false })
watch(() => props.refreshKey, () => {
  if (props.visible) reload()
  else stale = true
})
watch(() => props.visible, (shown) => {
  if (shown && stale) reload()
}, { immediate: true })
onBeforeUnmount(() => {
  alive = false
  token += 1
})
defineExpose({ reload })
</script>

<style scoped>
.gc { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; border-radius: 12px; background: var(--tint); box-shadow: inset 0 0 0 1px var(--line); font-size: 13px; min-width: 0; }
.gc-head { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
.gc-title { margin: 0; font-size: 14px; font-weight: 700; color: var(--fg); }
.gc-count { font-size: 12px; color: var(--fg-muted); }
.gc-spacer { flex: 1; }
.gc-live { margin: 0; min-height: 0; font-size: 12.5px; color: var(--fg-muted); }
.gc-live:empty { display: none; }
.gc-live.is-success { color: rgb(var(--accent-mint-rgb)); }
.gc-live.is-warn { color: rgb(var(--accent-amber-rgb, 217 119 6)); }
.gc-live.is-error { color: rgb(var(--accent-rose-rgb, 220 38 38)); }
.gc-problems { margin: 0; padding-left: 18px; font-size: 12.5px; color: var(--fg-muted); }
.gc-state { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; margin: 0; color: var(--fg-muted); line-height: 1.5; }
.gc-state.is-error { flex-direction: column; align-items: flex-start; color: var(--fg); }
.gc-body { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.gc-files { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; max-height: 220px; overflow-y: auto; }
.gc-row { display: flex; align-items: center; gap: 8px; padding: 2px 4px; border-radius: 8px; }
.gc-row.active { background: var(--tint-2); }
.gc-pick { all: unset; box-sizing: border-box; flex: 1; min-width: 0; display: flex; align-items: center; gap: 8px; min-height: 28px; cursor: pointer; border-radius: 6px; }
.gc-pick:focus-visible { outline: 2px solid rgb(var(--accent-sky-rgb)); outline-offset: 1px; }
.gc-kind { flex: none; min-width: 34px; text-align: center; padding: 1px 6px; border-radius: 6px; font-size: 11px; font-weight: 650; background: var(--tint-2); }
.gc-kind.k-added { color: rgb(var(--accent-mint-rgb)); }
.gc-kind.k-deleted { color: rgb(var(--accent-rose-rgb, 220 38 38)); }
.gc-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; font-size: 12px; }
.gc-dir { color: var(--fg-muted); }
.gc-badge { flex: none; font-size: 11.5px; font-weight: 600; }
.gc-badge.ok { color: rgb(var(--accent-mint-rgb)); }
.gc-badge.warn { color: rgb(var(--accent-amber-rgb, 217 119 6)); }
.gc-more, .gc-note { margin: 0; font-size: 12px; color: var(--fg-muted); }
.gc-pre { margin: 0; max-height: 320px; overflow: auto; padding: 8px 10px; border-radius: 8px; background: var(--bg, transparent); box-shadow: inset 0 0 0 1px var(--line); font-size: 12px; line-height: 1.45; font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; white-space: pre; }
.gc-pre:focus-visible { outline: 2px solid rgb(var(--accent-sky-rgb)); }
.dl { display: block; }
.dl.t-add { color: rgb(var(--accent-mint-rgb)); background: rgb(var(--accent-mint-rgb) / 0.1); }
.dl.t-del { color: rgb(var(--accent-rose-rgb, 220 38 38)); background: rgb(var(--accent-rose-rgb, 220 38 38) / 0.1); }
.dl.t-hunk { color: rgb(var(--accent-sky-rgb)); }
</style>

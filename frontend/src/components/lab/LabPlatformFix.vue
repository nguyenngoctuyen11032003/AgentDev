<template>
  <div class="pf">
    <details ref="reportEl" class="pf-report">
      <summary>{{ t('lab.platform_fix.report_summary') }}</summary>
      <pre class="pf-pre" tabindex="0" :aria-label="t('lab.platform_fix.report_summary')">{{ report }}</pre>
    </details>
    <div class="pf-actions">
      <button type="button" class="btn secondary sm" @click="copyReport">
        {{ copied ? t('lab.platform_fix.copied') : t('lab.platform_fix.copy') }}
      </button>
      <button type="button" class="btn secondary sm" aria-haspopup="dialog" @click="openDialog">
        {{ t('lab.platform_fix.request') }}
      </button>
    </div>
    <p v-if="copyFailed" class="pf-hint" role="status">{{ t('lab.platform_fix.copy_failed') }}</p>
    <span class="sr-only" role="status" aria-live="polite">{{ copied ? t('lab.platform_fix.copied') : '' }}</span>

    <BaseDialog v-model="open" :title="t('lab.platform_fix.dialog_title')" width="600px">
      <div class="pf-dialog">
        <p v-if="loading" class="pf-state" role="status">
          <span class="btn-spinner" aria-hidden="true"></span>
          {{ t('lab.platform_fix.loading') }}
        </p>

        <div v-else-if="loadError" class="pf-error" role="alert">
          <p>{{ t('lab.platform_fix.load_failed', { error: loadError }) }}</p>
          <p class="pf-hint">{{ t('lab.platform_fix.load_failed_hint') }}</p>
          <button type="button" class="btn secondary sm" @click="loadInfo">{{ t('lab.platform_fix.retry') }}</button>
        </div>

        <div v-else-if="result" ref="doneEl" class="pf-done" role="status" tabindex="-1">
          <p class="pf-done-title">{{ t('lab.platform_fix.done_title') }}</p>
          <p class="pf-safe">{{ t('lab.platform_fix.done_note') }}</p>
          <dl class="pf-facts">
            <template v-if="result.branch">
              <dt>{{ t('lab.platform_fix.branch') }}</dt>
              <dd><code>{{ result.branch }}</code></dd>
            </template>
            <template v-if="result.worktree">
              <dt>{{ t('lab.platform_fix.worktree') }}</dt>
              <dd><code>{{ result.worktree }}</code></dd>
            </template>
            <template v-if="result.brief_file">
              <dt>{{ t('lab.platform_fix.brief_file') }}</dt>
              <dd><code>{{ result.brief_file }}</code></dd>
            </template>
          </dl>
          <template v-if="list(result.actions).length">
            <h3 class="pf-sub">{{ t('lab.platform_fix.actions_title') }}</h3>
            <ul class="pf-list">
              <li v-for="(a, i) in list(result.actions)" :key="a.code || i">{{ localized('action', a) }}</li>
            </ul>
          </template>
          <template v-if="list(result.next_steps).length">
            <h3 class="pf-sub">{{ t('lab.platform_fix.next_steps_title') }}</h3>
            <ol class="pf-list">
              <li v-for="(s, i) in list(result.next_steps)" :key="s.code || i">{{ localized('next', s) }}</li>
            </ol>
          </template>
        </div>

        <div v-else-if="info && info.enabled === false" class="pf-error" role="alert">
          <p>{{ t('lab.platform_fix.errors.disabled') }}</p>
        </div>

        <form v-else-if="info" class="pf-form" @submit.prevent="confirm">
          <p class="pf-safe">{{ t('lab.platform_fix.intro') }}</p>
          <h3 class="pf-sub">{{ t('lab.platform_fix.steps_title') }}</h3>
          <ol class="pf-list">
            <li v-for="(s, i) in list(info.steps)" :key="s.code || i">{{ localized('step', s) }}</li>
          </ol>
          <h3 class="pf-sub">{{ t('lab.platform_fix.forbidden_title') }}</h3>
          <ul v-if="list(info.forbidden).length" class="pf-list">
            <li v-for="(f, i) in list(info.forbidden)" :key="f.path || i">
              <code>{{ f.path || itemText(f) }}</code><span v-if="f.path && kindLabel(f)" class="pf-note"> · {{ kindLabel(f) }}</span>
            </li>
          </ul>
          <p v-else class="pf-hint">{{ t('lab.platform_fix.none') }}</p>
          <h3 class="pf-sub">{{ t('lab.platform_fix.gates_title') }}</h3>
          <ul v-if="list(info.gates).length" class="pf-list">
            <li v-for="(g, i) in list(info.gates)" :key="g.code || i">
              {{ localized('gate', g) }}<template v-if="g.command">: <code>{{ g.command }}</code></template>
            </li>
          </ul>
          <p v-else class="pf-hint">{{ t('lab.platform_fix.none') }}</p>

          <label class="pf-check">
            <input v-model="understood" type="checkbox" required />
            <span>{{ t('lab.platform_fix.understand') }}</span>
          </label>
          <label class="pf-label" :for="passwordId">{{ t('lab.platform_fix.password_label') }}</label>
          <input
            :id="passwordId"
            ref="passwordEl"
            v-model="password"
            class="input"
            type="password"
            autocomplete="off"
            required
            :aria-invalid="submitError ? 'true' : undefined"
            :aria-describedby="`${passwordId}-hint`"
          />
          <p :id="`${passwordId}-hint`" class="pf-hint">{{ t('lab.platform_fix.password_hint') }}</p>
          <p v-if="submitError" class="pf-error-text" role="alert">{{ submitError }}</p>
        </form>
      </div>

      <template #footer>
        <button type="button" class="btn ghost sm" @click="open = false">
          {{ result ? t('lab.platform_fix.close') : t('lab.platform_fix.cancel') }}
        </button>
        <button
          v-if="info && info.enabled !== false && !result && !loading && !loadError"
          type="button"
          class="btn primary sm"
          :disabled="!canConfirm"
          @click="confirm"
        >
          <span v-if="submitting" class="btn-spinner" aria-hidden="true"></span>
          {{ submitting ? t('lab.platform_fix.confirming') : t('lab.platform_fix.confirm') }}
        </button>
      </template>
    </BaseDialog>
  </div>
</template>

<script setup>
// Platform findings: a copyable evidence report for a developer, and an explicit, password-gated request
// that only PREPARES a separate git branch + worktree (never merges, never touches the running app).
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseDialog from '@/components/common/BaseDialog.vue'
import { labPlatformFix, labPlatformFixInfo } from '@/api/client'
import { labErrorText } from '@/utils/labOutputs.js'
import { platformFixErrorCode } from '@/utils/labLayers.js'

const props = defineProps({
  jobId: { type: String, required: true },
  report: { type: String, required: true }
})

const { t, te } = useI18n()
const passwordId = `pf-password-${useId()}`
const reportEl = ref(null)
const doneEl = ref(null)
const passwordEl = ref(null)

const copied = ref(false)
const copyFailed = ref(false)
let copiedTimer = null
async function copyReport() {
  copyFailed.value = false
  try {
    await navigator.clipboard.writeText(props.report)
    copied.value = true
    clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // Clipboard unavailable: open the report so its text can be selected by hand.
    copyFailed.value = true
    if (reportEl.value) reportEl.value.open = true
  }
}

const open = ref(false)
const loading = ref(false)
const loadError = ref('')
const info = ref(null)
const understood = ref(false)
const password = ref('')
const submitting = ref(false)
const submitError = ref('')
const result = ref(null)
let alive = true

const list = (value) => (Array.isArray(value) ? value : [])
// Server items carry a stable `code` (forbidden files: `kind`) and `params`; the UI translates them and shows the
// server's English `text` only when this UI version has no key for that code.
const SHORT_SHA = 10
function localized(group, item) {
  const key = item && typeof item === 'object' && item.code ? `lab.platform_fix.${group}.${item.code}` : ''
  if (!key || !te(key)) return itemText(item)
  const params = { ...(item.params || {}) }
  if (params.head) params.head = String(params.head).slice(0, SHORT_SHA)
  return t(key, params)
}
const kindLabel = (item) => {
  const key = item?.kind ? `lab.platform_fix.kind.${item.kind}` : ''
  return key && te(key) ? t(key) : item?.text || ''
}
const itemText = (item) =>
  typeof item === 'string' ? item : item?.text || item?.label || item?.detail || item?.path || item?.name || JSON.stringify(item)
const errorText = (error) => {
  const code = platformFixErrorCode(error)
  if (code && te(`lab.platform_fix.errors.${code}`)) return t(`lab.platform_fix.errors.${code}`, error.params || {})
  return labErrorText(error, { t, te })
}

const canConfirm = computed(() => understood.value && !!password.value && !submitting.value)

async function loadInfo() {
  loading.value = true
  loadError.value = ''
  try {
    const data = await labPlatformFixInfo()
    if (alive) info.value = data
  } catch (error) {
    if (alive) loadError.value = errorText(error)
  } finally {
    if (alive) loading.value = false
  }
}

function openDialog() {
  open.value = true
  submitError.value = ''
  if (!info.value && !loading.value) loadInfo()
}

// Closing (Esc, backdrop, close or cancel button) forgets the password and the confirmation;
// BaseDialog returns focus to the request button.
watch(open, (isOpen) => {
  if (isOpen) return
  password.value = ''
  understood.value = false
  submitError.value = ''
})

async function confirm() {
  if (!canConfirm.value) return
  submitting.value = true
  submitError.value = ''
  const secret = password.value
  // The password never stays in the page, whatever the outcome.
  password.value = ''
  try {
    const data = await labPlatformFix(props.jobId, { password: secret })
    if (!alive) return
    result.value = data || {}
    submitting.value = false
    // The form (and the focused button) is gone: keep focus inside the dialog so Esc / Tab still work.
    await nextTick()
    doneEl.value?.focus()
  } catch (error) {
    if (!alive) return
    submitError.value = errorText(error)
    submitting.value = false
    await nextTick()
    passwordEl.value?.focus()
  }
}

onBeforeUnmount(() => {
  alive = false
  clearTimeout(copiedTimer)
  password.value = ''
})
</script>

<style scoped>
.pf { display: grid; gap: 8px; margin-top: 4px; }
.pf-report summary { cursor: pointer; font-size: 12.5px; font-weight: 600; width: fit-content; }
.pf-report summary:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; border-radius: 4px; }
.pf-pre {
  max-height: 280px;
  overflow: auto;
  margin: 6px 0 0;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  user-select: text;
}
.pf-pre:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.pf-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.pf-hint { margin: 0; font-size: 12.5px; color: var(--fg-muted); }
.pf-dialog { display: grid; gap: 10px; font-size: 13.5px; line-height: 1.55; }
.pf-state { display: flex; align-items: center; gap: 8px; margin: 0; color: var(--fg-muted); }
.pf-error { display: grid; gap: 6px; justify-items: start; }
.pf-error p { margin: 0; }
.pf-error-text { margin: 0; color: var(--danger); font-weight: 600; }
.pf-form { display: grid; gap: 8px; }
.pf-safe { margin: 0; padding: 8px 10px; border-radius: 8px; background: color-mix(in srgb, var(--success) 12%, transparent); }
.pf-sub { margin: 6px 0 0; font-size: 13px; font-weight: 650; }
.pf-list { margin: 0; padding-left: 20px; display: grid; gap: 3px; }
.pf-list code, .pf-facts code { overflow-wrap: anywhere; }
.pf-check { display: flex; align-items: flex-start; gap: 8px; margin-top: 6px; font-weight: 600; cursor: pointer; }
.pf-check input { margin-top: 3px; flex: none; width: 16px; height: 16px; }
.pf-note { color: var(--fg-muted); }
.pf-label { font-size: 12.5px; font-weight: 600; }
.pf-done { display: grid; gap: 8px; }
.pf-done:focus { outline: none; }
.pf-done-title { margin: 0; font-weight: 650; color: var(--success); }
.pf-facts { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 4px 12px; margin: 0; }
.pf-facts dt { color: var(--fg-muted); }
.pf-facts dd { margin: 0; min-width: 0; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>

<template>
  <section
    v-if="items.length || loadError || showLoading"
    class="pfs card"
    :aria-labelledby="headingId"
    :aria-busy="loading ? 'true' : undefined"
  >
    <header class="pfs-head">
      <h3 :id="headingId" class="pfs-title">
        {{ t('lab.platform_fixes.title') }}
        <span v-if="items.length" class="pfs-count">{{ items.length }}</span>
      </h3>
      <button v-if="items.length" type="button" class="btn ghost sm" :disabled="loading" @click="load">
        <span v-if="loading" class="btn-spinner" aria-hidden="true"></span>
        {{ t('lab.platform_fixes.refresh') }}
      </button>
    </header>
    <p v-if="items.length" class="pfs-hint">{{ t('lab.platform_fixes.hint') }}</p>

    <div v-if="loadError" class="pfs-error" role="alert">
      <p>{{ t('lab.platform_fixes.load_failed', { error: loadError }) }}</p>
      <p class="pfs-hint">{{ t('lab.platform_fixes.load_failed_hint') }}</p>
      <button type="button" class="btn secondary sm" :disabled="loading" @click="load">{{ t('lab.platform_fixes.retry') }}</button>
    </div>
    <p v-else-if="!items.length" class="pfs-hint" role="status">
      <span class="btn-spinner" aria-hidden="true"></span>
      {{ t('lab.platform_fixes.loading') }}
    </p>

    <ul v-if="items.length" class="pfs-list">
      <LabPlatformFixItem
        v-for="item in items"
        :key="item.id"
        :item="item"
        @merge="openDialog('merge', $event)"
        @discard="openDialog('discard', $event)"
        @refresh="load"
      />
    </ul>
  </section>

  <BaseDialog
    v-model="dialogOpen"
    :title="mode === 'merge' ? t('lab.platform_fixes.dialog.merge_title') : t('lab.platform_fixes.dialog.discard_title')"
    width="600px"
  >
    <div v-if="target" class="pfs-dialog">
      <div v-if="result" ref="doneEl" class="pfs-done" role="status" tabindex="-1">
        <p class="pfs-done-title">
          {{ mode === 'merge' ? t('lab.platform_fixes.dialog.merge_done') : t('lab.platform_fixes.dialog.discard_done') }}
        </p>
        <template v-if="list(result.actions).length">
          <h4 class="pfs-sub">{{ t('lab.platform_fixes.dialog.actions_title') }}</h4>
          <ul class="pfs-steps">
            <li v-for="(a, i) in list(result.actions)" :key="a.code || i">{{ localized('action', a) }}</li>
          </ul>
        </template>
        <template v-if="list(result.files).length">
          <h4 class="pfs-sub">{{ t('lab.platform_fixes.dialog.files_title') }}</h4>
          <ul class="pfs-steps">
            <li v-for="f in list(result.files)" :key="f"><code>{{ f }}</code></li>
          </ul>
        </template>
        <template v-if="list(result.next_steps).length">
          <h4 class="pfs-sub">{{ t('lab.platform_fixes.dialog.next_steps_title') }}</h4>
          <ol class="pfs-steps">
            <li v-for="(s, i) in list(result.next_steps)" :key="s.code || i">{{ localized('next', s) }}</li>
          </ol>
        </template>
      </div>

      <form v-else class="pfs-form" @submit.prevent="confirm">
        <template v-if="mode === 'merge'">
          <p class="pfs-intro">{{ t('lab.platform_fixes.dialog.merge_intro', { branch: target.branch }) }}</p>
          <ol class="pfs-steps">
            <li v-if="target.dirty_files">{{ t('lab.platform_fixes.dialog.merge_steps.commit', { n: target.dirty_files }) }}</li>
            <li v-else>{{ t('lab.platform_fixes.dialog.merge_steps.commit_none') }}</li>
            <li>{{ t('lab.platform_fixes.dialog.merge_steps.merge', { branch: target.branch }) }}</li>
            <li>{{ t('lab.platform_fixes.dialog.merge_steps.remove_worktree', { path: target.worktree }) }}</li>
            <li>{{ t('lab.platform_fixes.dialog.merge_steps.delete_branch', { branch: target.branch }) }}</li>
          </ol>
          <p class="pfs-safe">{{ t('lab.platform_fixes.dialog.no_push') }} {{ t('lab.platform_fixes.dialog.restart') }}</p>
          <label class="pfs-label" :for="messageId">{{ t('lab.platform_fixes.dialog.message_label') }}</label>
          <textarea
            :id="messageId"
            v-model="message"
            class="input pfs-message"
            rows="3"
            maxlength="5000"
            :aria-describedby="`${messageId}-hint`"
          ></textarea>
          <p :id="`${messageId}-hint`" class="pfs-hint">{{ t('lab.platform_fixes.dialog.message_hint') }}</p>
        </template>
        <template v-else>
          <p class="pfs-intro">{{ t('lab.platform_fixes.dialog.discard_intro', { branch: target.branch }) }}</p>
          <ul class="pfs-steps">
            <li>{{ t('lab.platform_fixes.dialog.discard_steps.remove_worktree', { path: target.worktree }) }}</li>
            <li>{{ t('lab.platform_fixes.dialog.discard_steps.delete_branch', { branch: target.branch }) }}</li>
          </ul>
          <p class="pfs-warn">{{ t('lab.platform_fixes.dialog.discard_steps.lost') }} {{ t('lab.platform_fixes.dialog.no_push') }}</p>
        </template>

        <label class="pfs-check">
          <input v-model="understood" type="checkbox" required data-autofocus />
          <span>{{ mode === 'merge' ? t('lab.platform_fixes.dialog.understand_merge') : t('lab.platform_fixes.dialog.understand_discard') }}</span>
        </label>
        <label class="pfs-label" :for="passwordId">{{ t('lab.platform_fixes.dialog.password_label') }}</label>
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
        <p :id="`${passwordId}-hint`" class="pfs-hint">{{ t('lab.platform_fixes.dialog.password_hint') }}</p>
        <p v-if="submitError" class="pfs-error-text" role="alert">{{ submitError }}</p>
      </form>
    </div>

    <template #footer>
      <button type="button" class="btn ghost sm" @click="dialogOpen = false">
        {{ result ? t('lab.platform_fixes.dialog.close') : t('lab.platform_fixes.dialog.cancel') }}
      </button>
      <button
        v-if="!result"
        type="button"
        :class="['btn', 'sm', mode === 'merge' ? 'primary' : 'danger']"
        :disabled="!canConfirm"
        @click="confirm"
      >
        <span v-if="submitting" class="btn-spinner" aria-hidden="true"></span>
        <template v-if="submitting">{{ t('lab.platform_fixes.dialog.confirming') }}</template>
        <template v-else-if="mode === 'merge'">{{ t('lab.platform_fixes.dialog.confirm_merge') }}</template>
        <template v-else>{{ t('lab.platform_fixes.dialog.confirm_discard') }}</template>
      </button>
    </template>
  </BaseDialog>
</template>

<script setup>
// Open platform fixes of this machine (not per job): verify, then commit + merge into main + clean up, or discard.
// Merge and discard need an explicit "I understand" + the source-fix password; nothing is ever pushed.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseDialog from '@/components/common/BaseDialog.vue'
import LabPlatformFixItem from './LabPlatformFixItem.vue'
import { labPlatformFixDiscard, labPlatformFixes, labPlatformFixMerge } from '@/api/client'
import { labErrorText } from '@/utils/labOutputs.js'
import { errorCodeOf, i18nParams, list, platformFixErrorText } from '@/utils/platformFixes.js'

const { t, te } = useI18n()
const uid = useId()
const headingId = `pfs-title-${uid}`
const passwordId = `pfs-password-${uid}`
const messageId = `pfs-message-${uid}`
const errorText = (error) => platformFixErrorText(error, { t, te, fallback: (e) => labErrorText(e, { t, te }) })

let alive = true

// --- List ---
const items = ref([])
const loading = ref(false)
const loadError = ref('')
// The loading line appears only when the first load is slow, so a machine without fixes shows nothing at all.
const showLoading = ref(false)
let loadingTimer = null
let loadSeq = 0
async function load() {
  const seq = ++loadSeq
  loading.value = true
  loadError.value = ''
  clearTimeout(loadingTimer)
  if (!items.value.length) loadingTimer = setTimeout(() => { if (alive && loading.value) showLoading.value = true }, 400)
  try {
    const data = await labPlatformFixes()
    if (!alive || seq !== loadSeq) return
    items.value = list(data?.items).filter((item) => item && item.id)
  } catch (error) {
    if (!alive || seq !== loadSeq) return
    loadError.value = errorText(error)
  } finally {
    if (alive && seq === loadSeq) {
      loading.value = false
      showLoading.value = false
      clearTimeout(loadingTimer)
    }
  }
}

// --- Merge / discard dialog ---
const dialogOpen = ref(false)
const mode = ref('merge')
const target = ref(null)
const understood = ref(false)
const password = ref('')
const message = ref('')
const submitting = ref(false)
const submitError = ref('')
const result = ref(null)
const passwordEl = ref(null)
const doneEl = ref(null)
let dialogSeq = 0

const canConfirm = computed(() => !!target.value && understood.value && !!password.value && !submitting.value)

const SHORT = ['commit', 'merge_commit', 'head']
function localized(group, item) {
  const key = item?.code ? `lab.platform_fixes.${group}.${item.code}` : ''
  if (!key || !te(key)) return item?.text || item?.code || ''
  const params = i18nParams(item.params)
  for (const k of SHORT) if (params[k] == null) params[k] = ''
  return t(key, params)
}

function openDialog(kind, item) {
  dialogSeq += 1
  mode.value = kind
  target.value = item
  result.value = null
  submitError.value = ''
  understood.value = false
  password.value = ''
  message.value = ''
  submitting.value = false
  dialogOpen.value = true
}

// Closing forgets the password and the confirmation; an answer still in flight is dropped (dialogSeq).
watch(dialogOpen, (isOpen) => {
  if (isOpen) return
  dialogSeq += 1
  password.value = ''
  understood.value = false
  submitting.value = false
  submitError.value = ''
})

async function confirm() {
  if (!canConfirm.value) return
  const seq = ++dialogSeq
  const kind = mode.value
  const id = target.value.id
  const secret = password.value
  // The password never stays in the page, whatever the outcome.
  password.value = ''
  submitting.value = true
  submitError.value = ''
  const stale = () => !alive || seq !== dialogSeq || target.value?.id !== id
  try {
    const data =
      kind === 'merge'
        ? await labPlatformFixMerge(id, { password: secret, message: message.value.trim() })
        : await labPlatformFixDiscard(id, { password: secret })
    // Done on the server even if the dialog was closed meanwhile: the list must drop the item.
    if (alive) load()
    if (stale()) return
    result.value = data || {}
    submitting.value = false
    await nextTick()
    doneEl.value?.focus()
  } catch (error) {
    if (stale()) return
    submitError.value = errorText(error)
    submitting.value = false
    if (errorCodeOf(error) === 'not_found') load()
    await nextTick()
    passwordEl.value?.focus()
  }
}

onMounted(load)
onBeforeUnmount(() => {
  alive = false
  clearTimeout(loadingTimer)
  password.value = ''
})
</script>

<style scoped>
.pfs { display: grid; gap: 10px; padding: 14px 16px; min-width: 0; }
.pfs-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 10px; }
.pfs-title { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 14.5px; font-weight: 650; }
.pfs-count { min-width: 22px; padding: 1px 7px; border-radius: 999px; font-size: 12px; font-weight: 600; text-align: center; color: var(--fg-muted); box-shadow: inset 0 0 0 1px var(--line); }
.pfs-hint { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 12.5px; color: var(--fg-muted); }
.pfs-error { display: grid; gap: 6px; justify-items: start; font-size: 13px; }
.pfs-error p { margin: 0; }
.pfs-list { margin: 0; padding: 0; list-style: none; display: grid; gap: 10px; }
.pfs-dialog { display: grid; gap: 10px; font-size: 13.5px; line-height: 1.55; }
.pfs-form, .pfs-done { display: grid; gap: 8px; }
.pfs-done:focus { outline: none; }
.pfs-done-title { margin: 0; font-weight: 650; color: var(--success); }
.pfs-intro { margin: 0; overflow-wrap: anywhere; }
.pfs-sub { margin: 4px 0 0; font-size: 13px; font-weight: 650; }
.pfs-steps { margin: 0; padding-left: 20px; display: grid; gap: 3px; overflow-wrap: anywhere; }
.pfs-safe { margin: 0; padding: 8px 10px; border-radius: 8px; background: color-mix(in srgb, var(--success) 12%, transparent); }
.pfs-warn { margin: 0; padding: 8px 10px; border-radius: 8px; background: color-mix(in srgb, var(--danger) 10%, transparent); font-weight: 600; }
.pfs-label { font-size: 12.5px; font-weight: 600; }
.pfs-message { resize: vertical; min-height: 60px; }
.pfs-check { display: flex; align-items: flex-start; gap: 8px; margin-top: 6px; font-weight: 600; cursor: pointer; }
.pfs-check input { margin-top: 3px; flex: none; width: 16px; height: 16px; }
.pfs-error-text { margin: 0; color: var(--danger); font-weight: 600; overflow-wrap: anywhere; }
@media (max-width: 720px) {
  .btn.sm { min-height: 44px; }
  .pfs-check { min-height: 44px; }
}
</style>

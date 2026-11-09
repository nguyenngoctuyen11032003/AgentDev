<template>
  <!-- "Tài khoản dùng thử": every account to try the product's app, next to its preview -->
  <section v-if="visible" class="acc" :aria-labelledby="titleId">
    <header class="acc-head">
      <button type="button" class="acc-toggle" :aria-expanded="open" :aria-controls="bodyId" @click="open = !open">
        <svg class="acc-chev" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg>
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="8" cy="15" r="4" /><path d="m10.8 12.2 8.2-8.2M16 7l2 2M14 9l2 2" /></svg>
        <strong :id="titleId">{{ $t('lab.accounts.title') }}</strong>
        <span v-if="total" class="acc-count">{{ total }}</span>
        <span v-else-if="state === 'ready'" class="acc-tag warn">{{ $t('lab.accounts.none_tag') }}</span>
      </button>
      <button v-if="open && !editing" type="button" class="btn secondary sm" @click="startAdd">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
        {{ $t('lab.accounts.add') }}
      </button>
    </header>

    <div v-show="open" :id="bodyId" class="acc-body">
      <!-- loading / error -->
      <div v-if="state === 'loading'" class="acc-skel" aria-hidden="true"><span></span><span></span></div>
      <p v-if="state === 'loading'" class="sr-only" role="status">{{ $t('lab.accounts.loading') }}</p>
      <div v-else-if="state === 'error'" class="acc-msg bad" role="alert">
        <span>{{ $t('lab.accounts.load_error') }}: {{ error }}</span>
        <button type="button" class="btn secondary sm" @click="load">{{ $t('lab.outputs.retry') }}</button>
      </div>

      <template v-else>
        <table v-if="rows.length" class="acc-table">
          <colgroup><col class="c-user" /><col class="c-pass" /><col /><col class="c-act" /></colgroup>
          <thead>
            <tr>
              <th scope="col">{{ $t('lab.login.username') }}</th>
              <th scope="col">{{ $t('lab.login.password') }}</th>
              <th scope="col">{{ $t('lab.accounts.note') }}</th>
              <th scope="col"><span class="sr-only">{{ $t('lab.accounts.actions') }}</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td :data-label="$t('lab.login.username')">
                <span class="acc-cell">
                  <code :title="row.username || undefined">{{ row.username || '—' }}</code>
                  <button v-if="row.username" type="button" class="acc-icon" :title="$t('lab.login.copy_username')" :aria-label="$t('lab.login.copy_username')" @click="copy(row.username, `${row.id}u`)">
                    <svg v-if="copied === `${row.id}u`" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 5 5 9-10" /></svg>
                    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a1 1 0 0 1 1-1h10" /></svg>
                  </button>
                </span>
              </td>
              <td :data-label="$t('lab.login.password')">
                <span class="acc-cell">
                  <code :class="{ masked: row.password && !shown.has(row.id) }">{{ row.password ? (shown.has(row.id) ? row.password : '••••••••') : '—' }}</code>
                  <template v-if="row.password">
                    <button type="button" class="acc-icon" :aria-pressed="shown.has(row.id)" :title="shown.has(row.id) ? $t('lab.accounts.hide') : $t('lab.accounts.show')" :aria-label="shown.has(row.id) ? $t('lab.accounts.hide') : $t('lab.accounts.show')" @click="toggleShown(row.id)">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /><path v-if="shown.has(row.id)" d="M4 4l16 16" /></svg>
                    </button>
                    <button type="button" class="acc-icon" :title="$t('lab.login.copy_password')" :aria-label="$t('lab.login.copy_password')" @click="copy(row.password, `${row.id}p`)">
                      <svg v-if="copied === `${row.id}p`" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 5 5 9-10" /></svg>
                      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a1 1 0 0 1 1-1h10" /></svg>
                    </button>
                  </template>
                </span>
              </td>
              <td :data-label="$t('lab.accounts.note')" class="acc-note">
                <span v-if="row.origin === 'found'" class="acc-tag" :title="row.source && row.source !== 'answer' ? row.source : undefined">{{ row.source && row.source !== 'answer' ? $t('lab.accounts.from_file', { file: baseName(row.source) }) : $t('lab.accounts.from_team') }}</span>
                <span v-if="row.note" class="acc-note-text">{{ row.note }}</span>
                <span v-if="row.origin === 'saved' && !row.note" class="acc-dash" aria-hidden="true">—</span>
              </td>
              <td class="acc-actions">
                <template v-if="row.origin === 'saved'">
                  <button type="button" class="acc-icon" :title="$t('lab.accounts.edit')" :aria-label="$t('lab.accounts.edit')" :disabled="saving" @click="startEdit(row.index)">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4Z" /></svg>
                  </button>
                  <button type="button" class="acc-icon danger" :title="$t('lab.accounts.delete')" :aria-label="$t('lab.accounts.delete')" :disabled="saving" @click="remove(row.index)">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></svg>
                  </button>
                </template>
                <button v-else type="button" class="acc-keep" :title="$t('lab.accounts.keep')" :aria-label="$t('lab.accounts.keep_one', { name: row.username || '—' })" :disabled="saving || isSaved(row)" @click="keepFound(row)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3h12v18l-6-4-6 4V3Z" /></svg>
                  <span>{{ $t('lab.accounts.save') }}</span>
                </button>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- nothing yet: say why, and how to get one -->
        <div v-else-if="!editing" class="acc-msg">
          <span v-if="login?.env?.password_var">
            {{ login.env.username
              ? $t('lab.login.env_hint', { user: login.env.username, user_var: login.env.user_var || '-', password_var: login.env.password_var })
              : $t('lab.login.env_hint_no_user', { password_var: login.env.password_var }) }}
          </span>
          <span v-else-if="login?.needs_login">{{ $t('lab.login.missing') }}</span>
          <span>{{ $t('lab.accounts.empty_hint') }}</span>
        </div>

        <!-- add / edit -->
        <form v-if="editing" class="acc-form" @submit.prevent="submit">
          <label>
            <span>{{ $t('lab.login.username') }}</span>
            <input ref="firstInput" v-model="draft.username" type="text" autocomplete="off" maxlength="200" />
          </label>
          <label>
            <span>{{ $t('lab.login.password') }}</span>
            <input v-model="draft.password" type="text" autocomplete="off" maxlength="200" spellcheck="false" />
          </label>
          <label class="wide">
            <span>{{ $t('lab.accounts.note') }}</span>
            <input v-model="draft.note" type="text" maxlength="300" :placeholder="$t('lab.accounts.note_placeholder')" />
          </label>
          <p v-if="formError" class="acc-form-error" role="alert">{{ formError }}</p>
          <div class="acc-form-actions">
            <button type="submit" class="btn primary sm" :disabled="saving">
              <span v-if="saving" class="btn-spinner" aria-hidden="true"></span>
              {{ $t('lab.accounts.save') }}
            </button>
            <button type="button" class="btn ghost sm" :disabled="saving" @click="cancel">{{ $t('lab.accounts.cancel') }}</button>
          </div>
        </form>
        <p class="acc-foot">{{ $t('lab.accounts.storage_note') }}</p>
      </template>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { labErrorText } from '@/utils/labOutputs.js'
import { confirmDialog } from '@/utils/confirm.js'
import { toast } from '@/utils/toast.js'

const props = defineProps({
  // {load(): {accounts}, save(rows): {accounts}} of the product (see utils/outputSources.js)
  api: { type: Object, required: true },
  // what the Lab found: { needs_login, credentials: [{username, password, source}], env? }
  login: { type: Object, default: null }
})

const { t, te } = useI18n()
const uid = useId()
const titleId = `acc-title-${uid}`
const bodyId = `acc-body-${uid}`

const open = ref(true)
const state = ref('loading') // loading | ready | error
const error = ref('')
const saved = ref([])
const saving = ref(false)
const editing = ref(false)
const editIndex = ref(-1)
const draft = reactive({ username: '', password: '', note: '' })
const formError = ref('')
const firstInput = ref(null)
const shown = ref(new Set())
const copied = ref('')
let copyTimer = null
let alive = true

const same = (a, b) => a.username === b.username && a.password === b.password
const found = computed(() => props.login?.credentials || [])
const isSaved = (row) => saved.value.some((s) => same(s, row))
// Saved accounts first (the user's own), then the ones the team reported that are not saved yet
const rows = computed(() => [
  ...saved.value.map((a, index) => ({ ...a, origin: 'saved', index, id: `s${index}` })),
  ...found.value.filter((c) => !isSaved(c)).map((c, index) => ({ ...c, note: '', origin: 'found', index, id: `f${index}` }))
])
const total = computed(() => rows.value.length)
// Only an app behind a login needs a test account. Without one (landing page, static site) the block shows only
// when the user saved accounts by hand, so they are never lost.
const needsLogin = computed(() => Boolean(props.login?.needs_login))
const visible = computed(() => needsLogin.value || saved.value.length > 0 || editing.value)

async function load() {
  state.value = 'loading'
  error.value = ''
  try {
    const res = await props.api.load()
    if (!alive) return
    saved.value = res?.accounts || []
    state.value = 'ready'
  } catch (err) {
    if (!alive) return
    error.value = labErrorText(err, { t, te })
    state.value = 'error'
  }
}

async function persist(next) {
  saving.value = true
  try {
    const res = await props.api.save(next)
    if (alive) saved.value = res?.accounts || []
    return true
  } catch (err) {
    toast.error(t('lab.accounts.save_error'), { detail: labErrorText(err, { t, te }) })
    return false
  } finally {
    saving.value = false
  }
}

function startAdd() {
  Object.assign(draft, { username: '', password: '', note: '' })
  editIndex.value = -1
  openForm()
}
function startEdit(index) {
  const row = saved.value[index]
  Object.assign(draft, { username: row.username, password: row.password, note: row.note || '' })
  editIndex.value = index
  openForm()
}
function openForm() {
  formError.value = ''
  editing.value = true
  open.value = true
  nextTick(() => firstInput.value?.focus())
}
function cancel() {
  editing.value = false
  formError.value = ''
}
async function submit() {
  const row = { username: draft.username.trim(), password: draft.password, note: draft.note.trim(), url: '' }
  if (!row.username && !row.password) {
    formError.value = t('lab.accounts.need_value')
    return
  }
  const next = [...saved.value]
  if (editIndex.value >= 0) next[editIndex.value] = { ...next[editIndex.value], ...row }
  else next.push(row)
  if (await persist(next)) editing.value = false
}
async function remove(index) {
  const row = saved.value[index]
  const ok = await confirmDialog({
    title: t('lab.accounts.delete_title'),
    message: t('lab.accounts.delete_message', { name: row.username || '—' }),
    confirmText: t('lab.accounts.delete'),
    tone: 'danger'
  })
  if (!ok || !alive) return
  await persist(saved.value.filter((_, i) => i !== index))
}
function keepFound(row) {
  if (isSaved(row)) return
  persist([...saved.value, { username: row.username, password: row.password, note: '', url: '' }])
}

// "code_workspace/README.md" -> "README.md" (the full path is in the tag's title)
const baseName = (path) => String(path).split('/').pop()

function toggleShown(id) {
  const next = new Set(shown.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  shown.value = next
}
async function copy(text, key) {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = key
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => { copied.value = '' }, 1500)
  } catch {
    toast.error(t('lab.login.copy_failed'))
  }
}

onMounted(load)
onBeforeUnmount(() => {
  alive = false
  clearTimeout(copyTimer)
})
</script>

<style scoped>
.acc { container: accounts / inline-size; margin-top: 12px; border-radius: 10px; background: var(--surface); box-shadow: inset 0 0 0 1px var(--line-strong); }
.acc-head { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; padding: 6px 8px 6px 6px; }
.acc-toggle { display: inline-flex; flex: 1 1 200px; align-items: center; gap: 8px; min-width: 0; min-height: 36px; padding: 4px 8px; border: 0; border-radius: 8px; background: transparent; color: var(--fg); font: inherit; font-size: 13.5px; text-align: left; cursor: pointer; }
.acc-toggle strong { white-space: nowrap; }
.acc-toggle:hover { background: var(--tint-2); }
.acc-toggle:focus-visible, .acc-icon:focus-visible, .acc-keep:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.acc-chev { flex: none; color: var(--fg-muted); transition: transform 0.15s ease; }
.acc-toggle[aria-expanded='true'] .acc-chev { transform: rotate(90deg); }
.acc-count { padding: 1px 8px; border-radius: 999px; font-size: 11.5px; font-weight: 700; color: var(--fg-muted); background: var(--tint-2); }
.acc-tag { display: inline-block; max-width: 100%; padding: 2px 8px; border-radius: 999px; font-size: 11.5px; font-weight: 600; color: var(--fg-muted); background: var(--tint-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; vertical-align: middle; }
.acc-tag.warn { color: var(--warn); background: color-mix(in srgb, var(--warn) 12%, transparent); }
.acc-body { padding: 0 12px 12px; border-top: 1px solid var(--line); }

.acc-table { width: 100%; margin-top: 4px; border-collapse: collapse; table-layout: fixed; font-size: 13px; }
.acc-table .c-user { width: 36%; }
.acc-table .c-pass { width: 28%; }
.acc-table .c-act { width: 96px; }
.acc-table th { padding: 8px; font-size: 11.5px; font-weight: 650; color: var(--fg-muted); text-align: left; border-bottom: 1px solid var(--line); }
.acc-table td { padding: 6px 8px; vertical-align: middle; border-bottom: 1px solid var(--line); }
.acc-table tbody tr:hover td { background: var(--tint); }
.acc-table tr:last-child td { border-bottom: 0; }
.acc-cell { display: flex; align-items: center; gap: 2px; min-width: 0; }
.acc-cell code { min-width: 0; padding: 3px 8px; border-radius: 6px; background: var(--tint-2); color: var(--fg); font-size: 12.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.acc-cell code.masked { flex: none; letter-spacing: 1px; }
.acc-note { color: var(--fg-muted); }
.acc-note > * + * { margin-left: 6px; }
.acc-note-text { overflow-wrap: anywhere; }
.acc-dash { color: var(--fg-muted); }
.acc-actions { white-space: nowrap; text-align: right; }
.acc-icon { display: inline-grid; flex: none; place-items: center; width: 30px; height: 30px; border: 0; border-radius: 7px; background: transparent; color: var(--fg-muted); cursor: pointer; transition: background-color 0.15s ease, color 0.15s ease; }
.acc-icon svg { width: 15px; height: 15px; }
.acc-icon:hover:not(:disabled) { color: var(--fg); background: var(--tint-2); }
.acc-icon.danger:hover:not(:disabled) { color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, transparent); }
.acc-icon:disabled, .acc-keep:disabled { opacity: 0.45; cursor: default; }
.acc-keep { display: inline-flex; align-items: center; gap: 5px; min-height: 30px; padding: 0 10px; border: 1px solid var(--line-strong); border-radius: 7px; background: transparent; color: var(--fg); font: inherit; font-size: 12.5px; font-weight: 600; cursor: pointer; transition: background-color 0.15s ease; }
.acc-keep svg { width: 13px; height: 13px; }
.acc-keep:hover:not(:disabled) { background: var(--tint-2); }

.acc-msg { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; margin-top: 10px; font-size: 13px; line-height: 1.55; color: var(--fg-muted); }
.acc-msg.bad { color: var(--danger); }
.acc-skel { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
.acc-skel span { height: 12px; border-radius: 6px; background: var(--tint-2); }
.acc-skel span + span { width: 60%; }

.acc-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 12px; margin-top: 10px; padding: 12px; border-radius: 8px; background: var(--tint); }
.acc-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 600; color: var(--fg-muted); }
.acc-form label.wide { grid-column: 1 / -1; }
.acc-form input { min-height: 36px; padding: 0 10px; border: 1px solid var(--line-strong); border-radius: 7px; background: var(--surface); color: var(--fg); font: inherit; font-size: 13px; }
.acc-form input:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 0; }
.acc-form-error { grid-column: 1 / -1; margin: 0; font-size: 12.5px; color: var(--danger); }
.acc-form-actions { grid-column: 1 / -1; display: flex; gap: 8px; }
.acc-foot { margin: 10px 0 0; font-size: 11.5px; line-height: 1.5; color: var(--fg-muted); }
.sr-only { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }

/* Narrow block (phone, or a narrow column): each account is a compact card -- label | value rows, the actions on
   the note row. A container query, since the block is often much narrower than the window. */
@container accounts (max-width: 560px) {
  .acc-head .btn { flex: 1 1 100%; justify-content: center; min-height: 44px; }
  .acc-table { table-layout: auto; }
  .acc-table colgroup, .acc-table thead { display: none; }
  .acc-table, .acc-table tbody { display: block; width: 100%; }
  .acc-table tr { display: grid; grid-template-columns: 68px minmax(0, 1fr) auto; align-items: center; gap: 4px 8px; padding: 10px 0; border-bottom: 1px solid var(--line); }
  .acc-table tr:last-child { border-bottom: 0; }
  .acc-table tbody tr:hover td { background: transparent; }
  .acc-table td { display: contents; }
  .acc-table td[data-label]::before { content: attr(data-label); grid-column: 1; font-size: 11.5px; color: var(--fg-muted); }
  .acc-table td .acc-cell { grid-column: 2 / -1; }
  .acc-table td.acc-note { grid-column: 1 / 3; display: flex; align-items: center; gap: 8px; min-width: 0; padding: 0; border: 0; }
  .acc-table td.acc-note::before { flex: 0 0 68px; }
  .acc-note > * + * { margin-left: 0; }
  .acc-table td.acc-actions { grid-column: 3; display: flex; justify-content: flex-end; gap: 2px; padding: 0; border: 0; }
  .acc-form { grid-template-columns: minmax(0, 1fr); }
  .acc-icon { width: 40px; height: 40px; }
  .acc-keep { min-height: 40px; }
}
@media (max-width: 640px) {
  .acc-icon { width: 44px; height: 44px; }
  .acc-keep, .acc-form input { min-height: 44px; }
}
@media (pointer: coarse) {
  .acc-icon { min-width: 44px; min-height: 44px; }
}
@media (prefers-reduced-motion: reduce) {
  .acc-chev, .acc-icon, .acc-keep { transition: none; }
}
</style>

<template>
  <Teleport to="body">
    <div v-if="open" class="dialog-backdrop" @mousedown.self="requestClose">
      <section
        ref="dialogEl"
        class="dialog"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        @keydown.esc.stop="requestClose"
      >
        <header class="dialog-head">
          <ProviderLogo :vendor="vendor.id" :label="vendor.label" :size="48" />
          <div class="dialog-heading">
            <h2 :id="titleId">{{ $t('connections.dialog_title', { provider: vendor.label }) }}</h2>
            <p>{{ $t('connections.dialog_subtitle') }}</p>
          </div>
          <button type="button" class="icon-btn" :aria-label="$t('connections.close')" @click="requestClose">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </header>

        <div class="dialog-body">
          <!-- Step 1: how to sign in -->
          <div class="method-grid" role="radiogroup" :aria-label="$t('connections.auth_method')">
            <button
              v-for="option in methods"
              :key="option.key"
              type="button"
              role="radio"
              class="method-card"
              :class="{ 'is-selected': method === option.key }"
              :aria-checked="method === option.key"
              @click="selectMethod(option.key)"
            >
              <span class="method-icon" aria-hidden="true">
                <svg v-if="option.key === 'key'" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="15" r="4" /><path d="M10.8 12.2 20 3m-4 4 3 3m-6-1 2 2" /></svg>
                <svg v-else viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" /></svg>
              </span>
              <span class="method-text">
                <span class="method-title">
                  {{ option.key === 'key' ? $t('connections.method_key_title') : $t('connections.method_account_title') }}
                  <em v-if="option.key !== 'key'" class="pill pill-accent">{{ $t('connections.recommended') }}</em>
                </span>
                <span class="method-desc">{{ methodDescription(option) }}</span>
              </span>
              <span class="method-radio" aria-hidden="true"></span>
            </button>
          </div>

          <label class="field">
            <span class="field-label">{{ $t('connections.label_optional') }}</span>
            <input v-model="form.label" class="input" maxlength="80" :placeholder="defaultLabel" />
          </label>

          <!-- Step 2: details for the chosen method -->
          <div class="detail">
            <!-- Account sign-in through a local CLI -->
            <template v-if="authType === 'cli'">
              <p v-if="!cliStatus" class="note">{{ $t('connections.checking') }}</p>
              <template v-else>
                <div class="status-row" :class="cliReady ? 'is-ok' : 'is-warn'">
                  <span class="status-dot" aria-hidden="true"></span>
                  <span>{{ cliStateText }}</span>
                </div>
                <p v-if="!cliStatus.installed" class="note">{{ $t('connections.cli_install_hint', { cli: cliBinary }) }}</p>
                <p v-else-if="!login.session" class="note">
                  {{ cliReady ? $t('connections.cli_use_current_hint') : $t('connections.cli_login_needed_hint') }}
                </p>
                <p v-if="cliStatus.installed && !login.session" class="note">
                  {{ vendor.cliTools ? $t('connections.cli_hint_tools') : $t('connections.cli_hint') }}
                </p>

                <div v-if="cliStatus.installed" class="login-box">
                  <template v-if="!login.session && cliReady">
                    <button type="button" class="link-btn" :disabled="login.busy" @click="startLogin">
                      {{ login.busy ? $t('connections.login_starting') : $t('connections.login_switch') }}
                    </button>
                    <p class="note">{{ $t('connections.login_switch_warning') }}</p>
                  </template>

                  <template v-else>
                    <ol class="steps">
                      <li class="step is-active">
                        <span class="step-num">1</span>
                        <div>
                          <p>{{ $t('connections.login_step_open') }}</p>
                          <div class="step-actions">
                            <a :href="login.session.url" target="_blank" rel="noopener noreferrer" class="btn btn-small">{{ $t('connections.login_open_link') }}</a>
                            <button type="button" class="btn btn-ghost btn-small" @click="copyLoginUrl">{{ $t('connections.login_copy_link') }}</button>
                          </div>
                        </div>
                      </li>
                      <li class="step is-active">
                        <span class="step-num">2</span>
                        <div v-if="login.session.mode === 'paste'">
                          <p>{{ $t('connections.login_step_copy_code') }}</p>
                          <div class="code-row">
                            <input
                              v-model="login.code"
                              class="input"
                              autocomplete="off"
                              spellcheck="false"
                              :placeholder="$t('connections.login_code_placeholder')"
                              @keydown.enter.prevent="submitLoginCode"
                            />
                            <button type="button" class="btn btn-primary" :disabled="login.busy || !login.code.trim()" @click="submitLoginCode">
                              {{ login.busy ? $t('connections.login_verifying') : $t('connections.login_confirm') }}
                            </button>
                          </div>
                        </div>
                        <div v-else>
                          <p>{{ $t('connections.login_step_device') }}</p>
                          <code class="device-code">{{ login.session.deviceCode }}</code>
                          <p class="note">{{ $t('connections.login_waiting_device') }}</p>
                        </div>
                      </li>
                    </ol>
                    <button type="button" class="link-btn" @click="cancelLogin">{{ $t('connections.login_cancel') }}</button>
                  </template>
                  <p v-if="login.error" class="alert" role="alert">{{ login.error }}</p>
                </div>
              </template>
            </template>

            <!-- Account sign-in with Google OAuth -->
            <template v-else-if="authType === 'oauth'">
              <div v-if="oauthConfigured === false" class="status-row is-warn">
                <span class="status-dot" aria-hidden="true"></span>
                <span>{{ $t('connections.oauth_not_configured') }}</span>
              </div>
              <p class="note">{{ $t('connections.oauth_hint') }}</p>
            </template>

            <!-- API key -->
            <template v-else>
              <label class="field">
                <span class="field-label">{{ $t('connections.api_key') }}</span>
                <span class="input-wrap">
                  <input
                    ref="keyInput"
                    v-model="form.apiKey"
                    class="input"
                    :type="showKey ? 'text' : 'password'"
                    autocomplete="off"
                    spellcheck="false"
                    :placeholder="vendor.envKeyHint ? `\${${vendor.envKeyHint}}` : ''"
                  />
                  <button type="button" class="input-toggle" @click="showKey = !showKey">
                    {{ showKey ? $t('connections.hide_key') : $t('connections.show_key') }}
                  </button>
                </span>
                <span class="field-hint">{{ $t('connections.api_key_hint', { example: '${ENV_KEY}' }) }}</span>
              </label>

              <details class="advanced">
                <summary>{{ $t('connections.advanced') }}</summary>
                <label class="field">
                  <span class="field-label">{{ $t('connections.base_url') }}</span>
                  <input v-model="form.baseUrl" class="input" :placeholder="vendor.defaultBaseUrl" spellcheck="false" />
                </label>
              </details>
            </template>
          </div>
        </div>

        <footer class="dialog-foot">
          <p class="privacy">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>
            {{ $t('connections.privacy') }}
          </p>
          <div class="foot-actions">
            <button type="button" class="btn btn-ghost" @click="requestClose">{{ $t('connections.cancel') }}</button>
            <button type="button" class="btn btn-primary" :disabled="!canSubmit || saving || login.busy" @click="submit">
              {{ submitLabel }}
            </button>
          </div>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup>
defineOptions({ name: 'ConnectDialog' })
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ProviderLogo from './ProviderLogo.vue'
import {
  cancelCliLogin,
  createConnection,
  fetchCliStatus,
  fetchGoogleOAuthStatus,
  pollCliLogin,
  pollGoogleOAuth,
  startCliLogin,
  startGoogleOAuth,
  submitCliLoginCode
} from '@/api/client'
import { toast } from '@/utils/toast'

const props = defineProps({
  open: { type: Boolean, default: false },
  vendor: { type: Object, required: true }
})
const emit = defineEmits(['close', 'created'])

const { t } = useI18n()
const titleId = `connect-title-${Math.random().toString(36).slice(2, 8)}`
const dialogEl = ref(null)
const keyInput = ref(null)

const form = reactive({ label: '', apiKey: '', baseUrl: '' })
const showKey = ref(false)
const saving = ref(false)
const method = ref('key')
const cliStatus = ref(null)
const oauthConfigured = ref(null)

// "Account" covers whichever sign-in the vendor offers (CLI or Google OAuth).
const methods = computed(() => {
  const list = []
  const auth = props.vendor.authMethods || []
  if (auth.includes('cli')) list.push({ key: 'cli' })
  else if (auth.includes('oauth')) list.push({ key: 'oauth' })
  if (auth.includes('api_key')) list.push({ key: 'key' })
  return list
})

const authType = computed(() => (method.value === 'key' ? 'api_key' : method.value))
const cliBinary = computed(() => (props.vendor.id === 'anthropic' ? 'claude' : 'codex'))
const cliReady = computed(() => !!cliStatus.value?.installed && cliStatus.value.logged_in !== false)

const defaultLabel = computed(() =>
  t('connections.default_name', {
    provider: props.vendor.label,
    method: authType.value === 'api_key' ? t('connections.auth_api_key') : t('connections.method_account_short')
  })
)

const canSubmit = computed(() => {
  if (authType.value === 'api_key') return !!form.apiKey.trim()
  if (authType.value === 'cli') return !!cliStatus.value?.installed && !login.session
  return oauthConfigured.value !== false
})

const cliStateText = computed(() => {
  const status = cliStatus.value
  if (!status) return ''
  if (!status.installed) return t('connections.cli_not_installed')
  if (status.logged_in === false) return t('connections.cli_not_logged_in')
  return status.account
    ? t('connections.cli_signed_in_as', { account: status.account })
    : t('connections.cli_account_ready')
})

const submitLabel = computed(() => {
  if (saving.value) return t('connections.adding')
  if (authType.value === 'oauth') return t('connections.sign_in_google')
  if (authType.value === 'cli' && !cliReady.value) return t('connections.login_and_connect')
  return t('connections.add')
})

function methodDescription(option) {
  if (option.key === 'key') return t('connections.method_key_desc')
  return option.key === 'oauth' ? t('connections.method_oauth_desc') : t('connections.method_cli_desc')
}

// --- CLI account sign-in (like running `claude auth login`, then pasting the code) ---
const login = reactive({ session: null, code: '', busy: false, error: '' })
let loginTimer = null

function resetLogin() {
  clearInterval(loginTimer)
  loginTimer = null
  login.session = null
  login.code = ''
  login.busy = false
}

async function refreshCliStatus() {
  try {
    cliStatus.value = await fetchCliStatus(props.vendor.id)
  } catch {
    cliStatus.value = { installed: false, logged_in: null, detail: '' }
  }
}

async function finishLogin(result) {
  const succeeded = result.status === 'succeeded'
  resetLogin()
  if (!succeeded) {
    // Sign-in failed: nothing is created, the user can simply try again.
    login.error = result.message || t('connections.sign_in_failed')
    return
  }
  toast.success(t('connections.login_success'))
  await refreshCliStatus()
  await saveConnection()
}

async function startLogin() {
  login.error = ''
  login.busy = true
  try {
    login.session = await startCliLogin(props.vendor.id)
    login.busy = false
    if (login.session.mode === 'device') {
      loginTimer = setInterval(async () => {
        try {
          const state = await pollCliLogin(login.session.sessionId)
          if (state.status !== 'waiting') finishLogin(state)
        } catch (error) {
          resetLogin()
          login.error = error.message
        }
      }, 2000)
    }
  } catch (error) {
    login.error = error.message
    login.busy = false
  }
}

async function submitLoginCode() {
  login.error = ''
  login.busy = true
  try {
    finishLogin(await submitCliLoginCode(login.session.sessionId, login.code.trim()))
  } catch (error) {
    login.error = error.message
    login.busy = false
  }
}

async function cancelLogin() {
  const sessionId = login.session?.sessionId
  resetLogin()
  if (sessionId) {
    try {
      await cancelCliLogin(sessionId)
    } catch {
      // The attempt expires on its own.
    }
  }
}

async function copyLoginUrl() {
  try {
    await navigator.clipboard.writeText(login.session.url)
    toast.success(t('connections.login_link_copied'))
  } catch {
    toast.warning(login.session.url)
  }
}

// --- Google OAuth (popup + polling) ---
// Stops the poll + message listener if the dialog unmounts mid sign-in.
let stopGoogleOAuth = null

function signInWithGoogle(label) {
  return new Promise((resolve, reject) => {
    startGoogleOAuth(label)
      .then(({ authUrl, state }) => {
        const popup = window.open(authUrl, 'agentdev-oauth', 'width=520,height=680')
        let timer = null
        let polling = false
        const stop = () => {
          clearInterval(timer)
          window.removeEventListener('message', onMessage)
          if (stopGoogleOAuth === stop) stopGoogleOAuth = null
        }
        const finish = (fn, value) => {
          stop()
          fn(value)
        }
        const onMessage = (event) => {
          if (event.origin === window.location.origin && event.data?.type === 'agentdev-oauth') {
            if (event.data.ok) finish(resolve, true)
            else finish(reject, new Error(t('connections.sign_in_failed')))
          }
        }
        window.addEventListener('message', onMessage)
        stopGoogleOAuth?.()
        stopGoogleOAuth = stop
        timer = setInterval(async () => {
          // A slow poll must not overlap the next one.
          if (polling) return
          polling = true
          try {
            const { status } = await pollGoogleOAuth(state)
            if (status === 'done') finish(resolve, true)
            else if (status === 'error') finish(reject, new Error(t('connections.sign_in_failed')))
            else if (popup?.closed) finish(reject, new Error(t('connections.sign_in_cancelled')))
          } catch (error) {
            finish(reject, error)
          } finally {
            polling = false
          }
        }, 1500)
      })
      .catch(reject)
  })
}

async function prepareMethod() {
  login.error = ''
  if (login.session) await cancelLogin()
  if (authType.value === 'cli') {
    cliStatus.value = null
    await refreshCliStatus()
  } else if (authType.value === 'oauth' && oauthConfigured.value === null) {
    try {
      oauthConfigured.value = (await fetchGoogleOAuthStatus()).configured
    } catch {
      oauthConfigured.value = false
    }
  }
}

function selectMethod(key) {
  if (method.value === key) return
  method.value = key
  prepareMethod()
}

// Creates the connection. For account sign-in the server re-checks that the account is really
// signed in, so a failed or cancelled login never leaves a connection behind.
async function saveConnection() {
  saving.value = true
  const label = form.label.trim() || defaultLabel.value
  try {
    if (authType.value === 'oauth') {
      await signInWithGoogle(label)
    } else {
      const isKey = authType.value === 'api_key'
      await createConnection({
        vendor: props.vendor.id,
        label,
        apiKey: isKey ? form.apiKey : '',
        baseUrl: isKey ? form.baseUrl : '',
        authType: authType.value
      })
    }
    toast.success(t('connections.added'))
    emit('created')
    emit('close')
  } catch (error) {
    login.error = error.message
    toast.error(error.message)
  } finally {
    saving.value = false
  }
}

async function submit() {
  // Not signed in yet: sign in first; the connection is created only after that succeeds.
  if (authType.value === 'cli' && !cliReady.value) {
    await startLogin()
    return
  }
  await saveConnection()
}

function requestClose() {
  if (saving.value) return
  emit('close')
}

watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) {
      if (login.session) cancelLogin()
      return
    }
    Object.assign(form, { label: '', apiKey: '', baseUrl: '' })
    showKey.value = false
    login.error = ''
    method.value = methods.value[0]?.key || 'key'
    await prepareMethod()
    await nextTick()
    ;(keyInput.value || dialogEl.value?.querySelector('button.method-card'))?.focus()
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  if (login.session) cancelCliLogin(login.session.sessionId).catch(() => {})
  clearInterval(loginTimer)
  stopGoogleOAuth?.()
})
</script>

<style scoped>
.dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9000;
  display: grid;
  place-items: center;
  padding: 24px 16px;
  overflow-y: auto;
  background: rgb(8 8 10 / 0.66);
  backdrop-filter: blur(6px);
  animation: fade 0.16s ease-out;
}

.dialog {
  box-sizing: border-box;
  width: min(560px, 100%);
  max-height: calc(100dvh - 48px);
  display: flex;
  flex-direction: column;
  border-radius: 20px;
  border: 1px solid var(--line-4);
  background: var(--surface-1);
  color: var(--text-1);
  box-shadow: 0 32px 80px -24px rgb(0 0 0 / 0.7);
  animation: rise 0.2s cubic-bezier(0.2, 0.8, 0.2, 1);
}

@keyframes fade {
  from { opacity: 0; }
}

@keyframes rise {
  from { opacity: 0; transform: translateY(10px) scale(0.985); }
}

@media (prefers-reduced-motion: reduce) {
  .dialog-backdrop,
  .dialog {
    animation: none;
  }
}

.dialog-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px 22px 16px;
}

.dialog-heading {
  flex: 1;
  min-width: 0;
}

.dialog-heading h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.dialog-heading p {
  margin: 2px 0 0;
  font-size: 13px;
  color: var(--text-muted-4);
}

.icon-btn {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--text-muted-4);
  cursor: pointer;
}

.icon-btn:hover {
  background: var(--surface-3);
  color: var(--text-1);
}

.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 4px 22px 20px;
  overflow-y: auto;
}

/* ---- method picker ---- */
.method-grid {
  display: grid;
  gap: 10px;
}

.method-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid var(--line-4);
  background: var(--surface-2);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.method-card:hover {
  border-color: var(--accent-sky);
}

.method-card.is-selected {
  border-color: var(--accent-indigo);
  background: color-mix(in srgb, var(--accent-indigo) 9%, var(--surface-2));
}

.method-icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 11px;
  background: var(--surface-3);
  color: var(--accent-sky);
}

.method-text {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.method-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
}

.method-desc {
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--text-muted-4);
}

.method-radio {
  flex: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid var(--line-4);
}

.method-card.is-selected .method-radio {
  border-color: var(--accent-indigo);
  background: radial-gradient(circle, var(--accent-indigo) 0 4px, transparent 5px);
}

.pill {
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-style: normal;
  font-weight: 600;
}

.pill-accent {
  background: color-mix(in srgb, var(--accent-mint) 16%, transparent);
  color: var(--accent-mint);
}

/* ---- detail ---- */
.detail {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.note {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--text-muted-4);
}

.status-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 600;
  background: var(--surface-2);
}

.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--text-muted-6);
}

.status-row.is-ok {
  color: var(--accent-mint);
}

.status-row.is-ok .status-dot {
  background: var(--accent-mint);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent-mint) 18%, transparent);
}

.status-row.is-warn {
  color: #ffd27a;
}

.status-row.is-warn .status-dot {
  background: #ffd27a;
}

.login-box {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}

.steps {
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
  margin: 0;
  padding: 16px;
  list-style: none;
  border-radius: 14px;
  background: var(--surface-2);
  border: 1px solid var(--line-4);
}

.step {
  display: flex;
  gap: 12px;
}

.step p {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.5;
}

.step > div {
  flex: 1;
  min-width: 0;
}

.step-num {
  display: grid;
  flex: none;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  background: color-mix(in srgb, var(--accent-indigo) 22%, transparent);
  color: var(--accent-indigo);
}

.step-actions,
.code-row {
  display: flex;
  gap: 8px;
}

.device-code {
  display: inline-block;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 18px;
  letter-spacing: 0.12em;
  background: var(--surface-3);
}

.alert {
  margin: 0;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 13px;
  color: var(--danger-soft);
  background: color-mix(in srgb, var(--danger) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--danger) 35%, transparent);
  overflow-wrap: anywhere;
}

/* ---- fields ---- */
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 13px;
  font-weight: 600;
}

.field-hint {
  font-size: 12px;
  color: var(--text-muted-4);
}

.input {
  box-sizing: border-box;
  width: 100%;
  padding: 11px 13px;
  border-radius: 10px;
  border: 1px solid var(--line-4);
  background: var(--surface-2);
  color: var(--text-1);
  font: inherit;
  font-size: 14px;
}

.input::placeholder {
  color: var(--text-muted-6);
}

.input:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 1px;
}

.input-wrap {
  position: relative;
  display: block;
}

.input-wrap .input {
  padding-right: 74px;
}

.input-toggle {
  position: absolute;
  top: 50%;
  right: 8px;
  transform: translateY(-50%);
  padding: 4px 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted-4);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.input-toggle:hover {
  color: var(--text-1);
}

.advanced summary {
  width: fit-content;
  margin-bottom: 10px;
  font-size: 13px;
  color: var(--text-muted-4);
  cursor: pointer;
}

/* ---- buttons ---- */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px 16px;
  border-radius: 10px;
  border: 1px solid var(--line-4);
  background: var(--surface-3);
  color: var(--text-1);
  font: inherit;
  font-size: 13.5px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, transform 0.1s;
}

.btn:hover:not(:disabled) {
  border-color: var(--accent-sky);
}

.btn:active:not(:disabled) {
  transform: translateY(1px);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-small {
  padding: 6px 12px;
  font-size: 12.5px;
}

.btn-ghost {
  border-color: transparent;
  background: transparent;
  color: var(--text-muted-4);
}

.btn-primary {
  border-color: transparent;
  background: linear-gradient(135deg, var(--accent-indigo), var(--accent-sky));
  color: #101418;
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(1.06);
}

.link-btn {
  padding: 0;
  border: 0;
  background: none;
  color: var(--text-muted-4);
  font: inherit;
  font-size: 12.5px;
  text-decoration: underline;
  cursor: pointer;
}

.dialog-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 22px;
  border-top: 1px solid var(--line-4);
}

.privacy svg {
  flex: none;
}

.privacy {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  max-width: 28ch;
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-muted-4);
}

.foot-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 2px;
}
</style>

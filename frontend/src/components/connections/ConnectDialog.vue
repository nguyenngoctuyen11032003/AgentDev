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
        <button type="button" class="icon-btn close-btn" :aria-label="$t('connections.close')" @click="requestClose">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>

        <header class="dialog-head">
          <ProviderLogo :vendor="vendor.id" :label="vendor.label" :size="56" />
          <h2 :id="titleId">{{ $t('connections.login_heading', { provider: vendor.label }) }}</h2>
          <p>{{ $t('connections.dialog_subtitle') }}</p>
        </header>

        <div class="dialog-body">
          <!-- Sign-in method: stacked options, like the login picker in the VS Code extensions -->
          <div v-if="!login.session" class="method-list" role="radiogroup" :aria-label="$t('connections.auth_method')">
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
                <svg v-if="option.key === 'device'" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></svg>
                <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" /></svg>
              </span>
              <span class="method-text">
                <span class="method-title">
                  {{ methodTitle(option) }}
                  <em v-if="option.key === 'cli' || option.key === 'oauth'" class="pill pill-accent">{{ $t('connections.recommended') }}</em>
                </span>
                <span class="method-desc">{{ methodDescription(option) }}</span>
              </span>
              <span class="method-radio" aria-hidden="true"></span>
            </button>
          </div>

          <!-- Details for the chosen method -->
          <div class="detail">
            <!-- Account sign-in through a local CLI -->
            <template v-if="authType === 'cli'">
              <p v-if="!cliStatus" class="note"><span class="spinner" aria-hidden="true"></span>{{ $t('connections.checking') }}</p>
              <template v-else>
                <div v-if="!login.session" class="status-row" :class="cliReady ? 'is-ok' : 'is-warn'">
                  <span class="status-dot" aria-hidden="true"></span>
                  <span>{{ cliStateText }}</span>
                </div>
                <p v-if="!cliStatus.installed" class="note">{{ $t('connections.cli_install_hint', { cli: cliBinary }) }}</p>
                <p v-else-if="!login.session" class="note">
                  {{ cliReady ? $t('connections.cli_use_current_hint') : $t('connections.cli_login_needed_hint') }}
                </p>
                <p v-if="cliStatus.installed && !login.session" class="note note-dim">
                  {{ vendor.cliTools ? $t('connections.cli_hint_tools') : $t('connections.cli_hint') }}
                </p>

                <div v-if="cliStatus.installed" class="login-box">
                  <template v-if="!login.session && cliReady">
                    <button type="button" class="link-btn" :disabled="login.busy" @click="startLogin">
                      {{ login.busy ? $t('connections.login_starting') : $t('connections.login_switch') }}
                    </button>
                    <p class="note note-dim">{{ $t('connections.login_switch_warning') }}</p>
                  </template>

                  <template v-else-if="login.session">
                    <p class="note browser-note">{{ $t('connections.login_browser_opened') }}</p>
                    <ol class="steps">
                      <li class="step">
                        <span class="step-num">1</span>
                        <div>
                          <p class="step-title">{{ $t('connections.step_signin') }}</p>
                          <p class="step-text">{{ $t('connections.login_step_open') }}</p>
                          <div class="step-actions">
                            <a :href="login.session.url" target="_blank" rel="noopener noreferrer" class="btn btn-small">{{ $t('connections.login_open_link') }}</a>
                            <button type="button" class="btn btn-ghost btn-small" @click="copyLoginUrl">{{ $t('connections.login_copy_link') }}</button>
                          </div>
                        </div>
                      </li>
                      <li class="step">
                        <span class="step-num">2</span>
                        <div v-if="login.session.mode === 'paste'">
                          <p class="step-title">{{ $t('connections.step_code') }}</p>
                          <p class="step-text">{{ $t('connections.login_step_copy_code') }}</p>
                          <div class="code-row">
                            <input
                              v-model="login.code"
                              class="input code-input"
                              autocomplete="off"
                              spellcheck="false"
                              :placeholder="$t('connections.login_code_placeholder')"
                              @keydown.enter.prevent="submitLoginCode"
                            />
                            <button type="button" class="btn" @click="pasteLoginCode">{{ $t('connections.login_paste') }}</button>
                          </div>
                          <button type="button" class="btn btn-primary btn-block" :disabled="login.busy || !login.code.trim()" @click="submitLoginCode">
                            {{ login.busy ? $t('connections.login_verifying') : $t('connections.login_confirm') }}
                          </button>
                          <p class="note waiting"><span class="spinner" aria-hidden="true"></span>{{ $t('connections.login_waiting_browser') }}</p>
                        </div>
                        <div v-else-if="login.session.mode === 'device'">
                          <p class="step-title">{{ $t('connections.login_step_device') }}</p>
                          <code class="device-code">{{ login.session.deviceCode }}</code>
                          <p class="note waiting"><span class="spinner" aria-hidden="true"></span>{{ $t('connections.login_waiting_device') }}</p>
                        </div>
                        <div v-else>
                          <p class="step-title">{{ $t('connections.step_finish') }}</p>
                          <p class="note waiting"><span class="spinner" aria-hidden="true"></span>{{ $t('connections.login_waiting_browser') }}</p>
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

            <details v-if="!login.session" class="advanced">
              <summary>{{ $t('connections.label_optional') }}</summary>
              <input v-model="form.label" class="input" maxlength="80" :placeholder="defaultLabel" />
            </details>
          </div>
        </div>

        <footer class="dialog-foot">
          <button
            v-if="!login.session"
            type="button"
            class="btn btn-primary btn-cta"
            :disabled="!canSubmit || saving || login.busy"
            @click="submit"
          >
            <span v-if="saving || login.busy" class="spinner" aria-hidden="true"></span>
            {{ login.busy ? $t('connections.login_starting') : submitLabel }}
          </button>
          <button type="button" class="btn btn-ghost btn-cta-sub" @click="requestClose">{{ $t('connections.cancel') }}</button>
          <p class="privacy">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>
            {{ $t('connections.privacy') }}
          </p>
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

const form = reactive({ label: '' })
const saving = ref(false)
const method = ref('cli')
const cliStatus = ref(null)
const oauthConfigured = ref(null)

// "Account" covers whichever sign-in the vendor offers (CLI or Google OAuth).
// OpenAI mirrors the Codex extension: ChatGPT sign-in, device code.
// API keys are not offered: connections always use an account sign-in.
const methods = computed(() => {
  const list = []
  const auth = props.vendor.authMethods || []
  const isOpenAI = props.vendor.id === 'openai'
  if (auth.includes('cli')) list.push({ key: 'cli', auth: 'cli', login: isOpenAI ? 'browser' : null })
  else if (auth.includes('oauth')) list.push({ key: 'oauth', auth: 'oauth', login: null })
  if (isOpenAI && auth.includes('cli')) list.push({ key: 'device', auth: 'cli', login: 'device' })
  return list
})

const currentMethod = computed(() => methods.value.find((m) => m.key === method.value))
const authType = computed(() => currentMethod.value?.auth || 'cli')
const loginMethod = computed(() => currentMethod.value?.login || null)
const cliBinary = computed(() => (props.vendor.id === 'anthropic' ? 'claude' : 'codex'))
const cliReady = computed(() => !!cliStatus.value?.installed && cliStatus.value.logged_in !== false)

const defaultLabel = computed(() =>
  t('connections.default_name', {
    provider: props.vendor.label,
    method: t('connections.method_account_short')
  })
)

const canSubmit = computed(() => {
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
  if (authType.value === 'cli' && !cliReady.value) {
    if (props.vendor.id === 'openai') {
      return loginMethod.value === 'device' ? t('connections.use_device_code') : t('connections.sign_in_chatgpt')
    }
    return t('connections.continue_account_named', { name: props.vendor.id === 'anthropic' ? 'Claude' : props.vendor.label })
  }
  return t('connections.add')
})

function methodTitle(option) {
  if (props.vendor.id === 'openai') {
    return option.key === 'device' ? t('connections.use_device_code') : t('connections.sign_in_chatgpt')
  }
  return t('connections.method_account_title')
}

function methodDescription(option) {
  if (props.vendor.id === 'openai' && option.key === 'cli') return t('connections.method_chatgpt_desc')
  if (option.key === 'device') return t('connections.method_device_desc')
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

let finishing = false

async function finishLogin(result) {
  // The poll and a pasted code can both report the end; only the first one counts.
  if (finishing) return
  finishing = true
  try {
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
  } finally {
    finishing = false
  }
}

async function startLogin() {
  login.error = ''
  login.busy = true
  try {
    const session = await startCliLogin(props.vendor.id, loginMethod.value)
    login.session = session
    login.busy = false
    // Like the VS Code extensions: open the sign-in page straight away (the link stays as a fallback).
    window.open(session.url, '_blank', 'noopener,noreferrer')
    if (session.mode === 'paste') {
      await nextTick()
      dialogEl.value?.querySelector('input.code-input')?.focus()
    }
    // Every mode is polled: the CLI exits once the browser sign-in completes, which finishes the connection.
    // (A pasted code is submitted separately, so the poll pauses while that request is running.)
    let polling = false
    loginTimer = setInterval(async () => {
      if (polling || login.busy || login.session?.sessionId !== session.sessionId) return
      polling = true
      try {
        const state = await pollCliLogin(session.sessionId)
        if (login.session?.sessionId === session.sessionId && state.status !== 'waiting') finishLogin(state)
      } catch (error) {
        if (login.session?.sessionId === session.sessionId && !login.busy) {
          resetLogin()
          login.error = error.message
        }
      } finally {
        polling = false
      }
    }, 2000)
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

async function pasteLoginCode() {
  try {
    login.code = (await navigator.clipboard.readText()).trim()
  } catch {
    dialogEl.value?.querySelector('input.code-input')?.focus()
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
      await createConnection({ vendor: props.vendor.id, label, authType: authType.value })
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
    form.label = ''
    login.error = ''
    method.value = methods.value[0]?.key || 'cli'
    await prepareMethod()
    await nextTick()
    dialogEl.value?.querySelector('button.method-card')?.focus()
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
  backdrop-filter: blur(4px);
  animation: fade 0.16s ease-out;
}

.dialog {
  position: relative;
  box-sizing: border-box;
  width: min(440px, 100%);
  max-height: calc(100dvh - 48px);
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  border: 1px solid var(--line-4);
  background: var(--surface-1);
  color: var(--text-1);
  box-shadow: 0 24px 64px -20px rgb(0 0 0 / 0.7);
  animation: rise 0.2s cubic-bezier(0.2, 0.8, 0.2, 1);
}

@keyframes fade {
  from { opacity: 0; }
}

@keyframes rise {
  from { opacity: 0; transform: translateY(8px) scale(0.99); }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .dialog-backdrop,
  .dialog {
    animation: none;
  }
}

/* ---- header: centered brand, like the extension sign-in screens ---- */
.dialog-head {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 32px 28px 18px;
  text-align: center;
}

.dialog-head h2 {
  margin: 12px 0 0;
  font-size: 20px;
  font-weight: 650;
  letter-spacing: -0.015em;
}

.dialog-head p {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted-4);
}

.icon-btn {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted-4);
  cursor: pointer;
}

.close-btn {
  position: absolute;
  top: 10px;
  right: 10px;
}

.icon-btn:hover {
  background: var(--surface-3);
  color: var(--text-1);
}

.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 0 28px 8px;
  overflow-y: auto;
}

/* ---- method list ---- */
.method-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.method-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 14px;
  border-radius: 8px;
  border: 1px solid var(--line-4);
  background: var(--surface-2);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.method-card:hover {
  border-color: color-mix(in srgb, var(--accent-sky) 60%, var(--line-4));
}

.method-card.is-selected {
  border-color: var(--accent-sky);
  background: color-mix(in srgb, var(--accent-sky) 8%, var(--surface-2));
}

.method-icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--surface-3);
  color: var(--text-muted-4);
}

.method-card.is-selected .method-icon {
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
  font-size: 13.5px;
  font-weight: 600;
}

.method-desc {
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-muted-4);
}

.method-radio {
  flex: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 1.5px solid var(--line-4);
}

.method-card.is-selected .method-radio {
  border-color: var(--accent-sky);
  background: radial-gradient(circle, var(--accent-sky) 0 4px, transparent 5px);
}

.pill {
  padding: 0 7px;
  border-radius: 999px;
  font-size: 10.5px;
  font-style: normal;
  font-weight: 600;
  line-height: 17px;
}

.pill-accent {
  background: color-mix(in srgb, var(--accent-mint) 16%, transparent);
  color: var(--accent-mint);
}

/* ---- detail ---- */
.detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.note {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--text-muted-4);
}

.note-dim {
  font-size: 12px;
  opacity: 0.85;
}

.browser-note {
  justify-content: center;
  text-align: center;
}

.spinner {
  flex: none;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  border: 2px solid color-mix(in srgb, currentColor 30%, transparent);
  border-top-color: currentColor;
  animation: spin 0.7s linear infinite;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 600;
  background: var(--surface-2);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted-6);
}

.status-row.is-ok {
  color: var(--accent-mint);
}

.status-row.is-ok .status-dot {
  background: var(--accent-mint);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent-mint) 18%, transparent);
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
  align-items: stretch;
  gap: 12px;
}

.login-box > .link-btn {
  align-self: center;
}

.steps {
  display: flex;
  flex-direction: column;
  gap: 18px;
  margin: 0;
  padding: 16px;
  list-style: none;
  border-radius: 8px;
  background: var(--surface-2);
  border: 1px solid var(--line-4);
}

.step {
  display: flex;
  gap: 12px;
}

.step > div {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.step-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}

.step-text {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-muted-4);
}

.step-num {
  display: grid;
  flex: none;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  font-size: 11.5px;
  font-weight: 700;
  background: color-mix(in srgb, var(--accent-sky) 20%, transparent);
  color: var(--accent-sky);
}

.step-actions,
.code-row {
  display: flex;
  gap: 8px;
}

.code-row .input {
  flex: 1;
  min-width: 0;
}

.device-code {
  align-self: flex-start;
  padding: 8px 14px;
  border-radius: 6px;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 0.14em;
  background: var(--surface-3);
}

.waiting {
  margin-top: 2px;
}

.alert {
  margin: 0;
  padding: 9px 12px;
  border-radius: 8px;
  font-size: 12.5px;
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
  font-size: 12.5px;
  font-weight: 600;
}

.field-hint {
  font-size: 11.5px;
  color: var(--text-muted-4);
}

.input {
  box-sizing: border-box;
  width: 100%;
  padding: 9px 12px;
  border-radius: 6px;
  border: 1px solid var(--line-4);
  background: var(--surface-2);
  color: var(--text-1);
  font: inherit;
  font-size: 13.5px;
}

.input::placeholder {
  color: var(--text-muted-6);
}

.input:focus-visible {
  outline: 1px solid var(--accent-sky);
  outline-offset: 0;
  border-color: var(--accent-sky);
}

.advanced summary {
  width: fit-content;
  margin-bottom: 8px;
  font-size: 12.5px;
  color: var(--text-muted-4);
  cursor: pointer;
}

.advanced summary:hover {
  color: var(--text-1);
}

.advanced:not([open]) summary {
  margin-bottom: 0;
}

/* ---- buttons ---- */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 6px;
  border: 1px solid var(--line-4);
  background: var(--surface-3);
  color: var(--text-1);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, filter 0.15s;
}

.btn:hover:not(:disabled) {
  border-color: var(--accent-sky);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-small {
  padding: 5px 11px;
  font-size: 12.5px;
}

.btn-ghost {
  border-color: transparent;
  background: transparent;
  color: var(--text-muted-4);
}

.btn-ghost:hover:not(:disabled) {
  border-color: transparent;
  color: var(--text-1);
}

.btn-primary {
  border-color: transparent;
  background: var(--accent-sky);
  color: #101418;
}

.btn-primary:hover:not(:disabled) {
  border-color: transparent;
  filter: brightness(1.08);
}

.btn-block {
  width: 100%;
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

.link-btn:hover {
  color: var(--text-1);
}

/* ---- footer: one full-width call to action ---- */
.dialog-foot {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
  padding: 16px 28px 20px;
}

.btn-cta {
  padding: 11px 16px;
  font-size: 14px;
}

.btn-cta-sub {
  padding: 6px 12px;
  font-size: 12.5px;
}

.privacy {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin: 6px 0 0;
  font-size: 11.5px;
  line-height: 1.4;
  text-align: center;
  color: var(--text-muted-6);
}

.privacy svg {
  flex: none;
}

:focus-visible {
  outline: 1px solid var(--accent-sky);
  outline-offset: 2px;
}
</style>

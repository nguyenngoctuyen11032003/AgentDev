<template>
  <!-- The demo account of an app behind a login: the tester needs it to open the preview and judge the app -->
  <div v-if="login && (login.needs_login || login.credentials?.length)" :class="['login-box', { missing: !login.credentials?.length }]">
    <p class="login-title">
      <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>
      <strong>{{ $t('lab.login.title') }}</strong>
    </p>
    <template v-if="login.credentials?.length">
      <p v-if="login.login_url" class="login-url">
        {{ $t('lab.login.page') }}: <a :href="login.login_url" target="_blank" rel="noopener noreferrer">{{ login.login_url }}</a>
      </p>
      <ul class="login-list">
        <li v-for="(c, i) in login.credentials" :key="i" class="login-item">
          <span class="login-field">
            <span class="login-key">{{ $t('lab.login.username') }}</span>
            <code>{{ c.username }}</code>
            <button type="button" class="login-copy" :aria-label="$t('lab.login.copy_username')" @click="copy(c.username, `u${i}`)">
              {{ copied === `u${i}` ? $t('lab.login.copied') : $t('lab.login.copy') }}
            </button>
          </span>
          <span class="login-field">
            <span class="login-key">{{ $t('lab.login.password') }}</span>
            <code>{{ c.password }}</code>
            <button type="button" class="login-copy" :aria-label="$t('lab.login.copy_password')" @click="copy(c.password, `p${i}`)">
              {{ copied === `p${i}` ? $t('lab.login.copied') : $t('lab.login.copy') }}
            </button>
          </span>
          <span v-if="c.source && c.source !== 'answer'" class="login-source">{{ $t('lab.login.from_file', { file: c.source }) }}</span>
        </li>
      </ul>
    </template>
    <!-- The app makes its account from environment variables: say which one to set -->
    <div v-else-if="login.env?.password_var" class="login-env">
      <p class="login-missing">
        {{ login.env.username
          ? $t('lab.login.env_hint', { user: login.env.username, user_var: login.env.user_var || '-', password_var: login.env.password_var })
          : $t('lab.login.env_hint_no_user', { password_var: login.env.password_var }) }}
      </p>
      <span class="login-field">
        <code>{{ login.env.password_var }}=</code>
        <button type="button" class="login-copy" :aria-label="$t('lab.login.copy_variable')" @click="copy(`${login.env.password_var}=`, 'env')">
          {{ copied === 'env' ? $t('lab.login.copied') : $t('lab.login.copy') }}
        </button>
      </span>
    </div>
    <p v-else class="login-missing">{{ $t('lab.login.missing') }}</p>
    <p v-if="copyError" class="login-missing" role="alert">{{ $t('lab.login.copy_failed') }}</p>
    <!-- The buttons keep their accessible name; the "copied" state is announced here -->
    <span class="sr-only" aria-live="polite">{{ copied ? $t('lab.login.copied') : '' }}</span>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref } from 'vue'

defineProps({
  // { needs_login, credentials: [{ username, password, source }], login_url }
  login: { type: Object, default: null }
})

const copied = ref('')
const copyError = ref(false)
let timer = null

async function copy(text, key) {
  copyError.value = false
  try {
    await navigator.clipboard.writeText(text)
    copied.value = key
    clearTimeout(timer)
    timer = setTimeout(() => { copied.value = '' }, 1500)
  } catch {
    copyError.value = true
  }
}

onBeforeUnmount(() => clearTimeout(timer))
</script>

<style scoped>
.login-box { margin: 10px 0 0; padding: 10px 12px; border-radius: 10px; background: color-mix(in srgb, var(--success) 8%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--success) 30%, transparent); }
.login-box.missing { background: color-mix(in srgb, var(--warn) 8%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--warn) 35%, transparent); }
.login-title { display: flex; align-items: center; gap: 6px; margin: 0; font-size: 13px; color: var(--fg); }
.login-url { margin: 6px 0 0; font-size: 13px; color: var(--fg-muted); word-break: break-all; }
.login-list { list-style: none; margin: 6px 0 0; padding: 0; display: grid; gap: 6px; }
.login-item { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 16px; font-size: 13px; }
.login-field { display: inline-flex; align-items: center; gap: 6px; min-width: 0; }
.login-key { color: var(--fg-muted); }
.login-field code { padding: 1px 6px; border-radius: 6px; background: var(--tint-2); color: var(--fg); word-break: break-all; }
.login-copy { padding: 2px 8px; border: 1px solid var(--border); border-radius: 6px; background: transparent; color: var(--fg); font-size: 12px; cursor: pointer; }
.sr-only { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
.login-copy:hover { background: var(--tint-2); }
.login-copy:focus-visible { outline: 2px solid var(--accent, currentColor); outline-offset: 2px; }
.login-source { font-size: 12px; color: var(--fg-muted); }
.login-env .login-field { margin-top: 6px; font-size: 13px; }
.login-missing { margin: 6px 0 0; font-size: 13px; line-height: 1.5; color: var(--fg); }
</style>
